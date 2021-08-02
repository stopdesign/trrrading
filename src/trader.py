import json  # noqa
import logging
import math
from typing import List
import pandas as pd
from datetime import datetime
from decimal import Decimal
from termcolor import cprint
from advisor import Advisor
from exchange import BaseExchange, all_exchanges
from notifications.alert import send_telegram  # noqa
from stats import AccountStats, TradeStats
from strategy import Signal
from settings import CAN_SHORT
from util import log_trade, log_trade_result

CURSOR_UP_ONE = "\x1b[1A"
ERASE_LINE = "\x1b[2K"


log = logging.getLogger("trader")


class Trader:
    exchange: BaseExchange = None

    def __init__(self, exchange, advisors, dt_start):
        cprint("Init trader", "white")

        self.can_short = CAN_SHORT
        self.reinvest_profit = False

        self.dt_start = datetime.strptime(dt_start, "%Y-%m-%d")
        self.advisors = advisors

        exchange_class = all_exchanges[exchange]
        self.exchange = exchange_class(advisors, dt_start=self.dt_start)
        self.exchange.on_event = self.on_event

        self.account_stats = AccountStats(self.exchange)
        self.trade_stats = TradeStats()

    def warm_up(self):
        cprint("\nHistorical data", "white")
        self.exchange.warm_up()

    def start(self):
        cprint("\nStart stream", "white")
        self.account_stats.snapshot()
        self.exchange.start_listen()
        self.stop()

    def stop(self):
        cprint("\nStop stream", "white")
        self.exchange.stop_listen()
        self.account_stats.snapshot()

    def final_info(self):
        df = pd.DataFrame(self.get_advisors()[0].strategy.data)
        if not df.empty:
            df.set_index("date", inplace=True)
            df = df[df.index > self.dt_start]
            df.to_csv("../front/data.csv")
        self.trade_stats.to_csv("../front/trades.csv")
        self.account_stats.to_csv("../front/stats.csv")
        self.account_stats.print_summary()  # RESULTS

    def on_event(self, event, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        # if dt >= self.dt_start and event != "quote":
        #     cprint(f"{dt}: EVENT {event} {symbol} {payload}", "white")

        if event == "bar":
            for advisor in self.get_advisors(symbol):
                advisor.on_bar(dt, payload)

        if event == "trade" and dt < self.dt_start:
            for advisor in self.get_advisors(symbol):
                advisor.test_price(dt, payload.price)

        if event == "trade" and dt >= self.dt_start:
            self.on_trade(dt, symbol, payload.price)

        if event == "quote":
            self.exchange.add_quote(dt, symbol, payload)

        if event in ["hour", "day", "after_trade"]:
            if dt >= self.dt_start:
                self.account_stats.snapshot()

        if event == "after_trade":
            self.trade_stats.on_trade(dt, symbol, payload)
            self.account_stats.on_trade(symbol, payload)
            self.account_stats.update_pl()
            log_trade_result(log, self.exchange, payload)

        return True

    def get_advisors(self, symbol=None) -> List[Advisor]:
        """
        Все советники для данного инструмента.
        """
        return [a for a in self.advisors if not symbol or a.instrument == symbol]

    def get_current_position(self, instrument):
        """
        Сколько сейчас в портфолио этой штуки.
        """
        positions = self.exchange.get_positions()
        return positions.get(instrument, BaseExchange.empty_position)["amount"]

    def get_advised_position(self, instrument):
        """
        Сколько сейчас в портфолио должно быть этой штуки,
        если бы сработали все исторические сигналы.
        """
        buying_power = self.get_buying_power()

        res = Decimal("0")
        for advisor in self.get_advisors(instrument):
            if advisor.state == Signal.LONG:
                price = self.exchange.get_price(instrument, "buy")
                amount = math.floor(buying_power / Decimal(price))
                res += amount
            if advisor.state == Signal.SHORT:
                price = self.exchange.get_price(instrument, "sell")
                amount = math.floor(buying_power / Decimal(price))
                res -= amount
            if advisor.state == Signal.CLOSE:
                res = Decimal(0)

        # Если нельзя шортить
        if not self.can_short:
            res = max(Decimal(0), res)

        return res

    def get_buying_power(self):
        """
        Сумма, которой может управлять один советник.

        Сейчас депозит делится равными долями между всеми.
        Если reinvest_profit выключен, то делится начальный депозит.
        """
        cash_to_use = self.exchange.net_value
        if not self.reinvest_profit:
            cash_to_use = min(self.exchange.cash_initial, cash_to_use)
        cnt = len(self.get_advisors())
        if cnt:
            return cash_to_use / cnt
        else:
            return 0

    def on_trade(self, dt: datetime, symbol, tr_price, volume=None):  # noqa
        """
        Тут торговля, если стратегия дала сигнал.
        Здесь же риск-менеджмент уровня аккаунта,
        контроль использования маржи.
        """
        # cprint(f"\nON_TRADE {dt} {symbol} {tr_price}", "cyan")
        # self.portfolio_info()

        # Протестировать новую цену (не добавляя в историю).
        # Получить суммарный объем на покупку/продажу по всем сигналам.
        can_buy, can_sell = self.test_new_price(symbol, dt, tr_price)

        # Это всё должно быть после тестирования новой цены // TODO: почему?
        cp = self.get_current_position(symbol)
        ap = self.get_advised_position(symbol)
        diff = ap - cp

        # Всё равно ничего сделать нельзя
        if not (diff and (can_buy or can_sell)):
            # cprint(f"SKIP: diff: {diff}, buy: {can_buy}, sell: {can_sell}")
            return

        # Посчитать, куда нужно торговать.
        # Скоректировать объем по возможностям, которые есть по сигналам.
        amount, side = 0, None
        if diff > 0:
            amount, side = min(abs(diff), can_buy), "buy"
        if diff < 0:
            amount, side = -min(abs(diff), can_sell), "sell"

        price = self.exchange.get_price(symbol, side)

        # Предлагаемое изменение должно быть больше минимального
        if abs(amount) < self.get_min_tradable_amount(price):
            amount, side = 0, None

        log_trade(log, dt, symbol, tr_price, price, cp, ap, amount, can_sell, can_buy)

        # Если есть все параметры — запустить сделку
        if price and amount:
            self.exchange.trade(side, abs(amount), symbol, dt)

    def get_min_tradable_amount(self, price):
        """
        Минимальное количество акций, которое стоит покупать/продавать.
        """
        symbols = list(set([a.instrument for a in self.get_advisors()]))
        cash_per_symbol = self.exchange.net_value / len(symbols)
        min_tradable_amount = math.floor((cash_per_symbol / 10) / Decimal(price))
        min_tradable_amount = max(1, min_tradable_amount)
        return min_tradable_amount

    def test_new_price(self, instrument, dt, price):
        """
        Посчитать суммарный объем покупки и продажи,
        который предлагают советники для новой цены
        """
        # Сумма, которой может управлять один советник
        buying_power = self.get_buying_power()

        total_buy, total_sell = Decimal("0"), Decimal("0")

        for advisor in self.get_advisors(instrument):
            current_state = advisor.state
            signal = advisor.test_price(dt, price)

            if signal == Signal.LONG:
                cur_price = self.exchange.get_price(instrument, "buy")
                amount = math.floor(buying_power / Decimal(cur_price))
                if current_state == Signal.SHORT:
                    total_buy += amount * 2
                elif current_state == Signal.LONG:
                    total_buy += 0
                else:
                    total_buy += amount

            if signal == Signal.SHORT:
                cur_price = self.exchange.get_price(instrument, "sell")
                amount = math.floor(buying_power / Decimal(cur_price))
                if current_state == Signal.LONG:
                    total_sell += amount * 2
                elif current_state == Signal.SHORT:
                    total_sell += 0
                else:
                    total_sell += amount

            if signal == Signal.CLOSE:
                if current_state == Signal.LONG:
                    cur_price = self.exchange.get_price(instrument, "sell")
                    amount = math.floor(buying_power / Decimal(cur_price))
                    total_sell += amount
                elif current_state == Signal.SHORT:
                    cur_price = self.exchange.get_price(instrument, "buy")
                    amount = math.floor(buying_power / Decimal(cur_price))
                    total_buy += amount

        return total_buy, total_sell
