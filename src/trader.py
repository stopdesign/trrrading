import json  # noqa
import logging
import math
from collections import defaultdict
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

    def __init__(self, exchange, advisors, target_margin, dt_start=None):
        cprint("Init trader", "white")

        self.can_short = CAN_SHORT
        self.reinvest_profit = False

        # Значение used margin, к которому должен стремиться депозит
        self.target_margin = target_margin

        self.advisors = advisors

        exchange_class = all_exchanges[exchange]

        if exchange_class.backtest:
            self.dt_start = datetime.strptime(dt_start, "%Y-%m-%d")
        else:
            self.dt_start = datetime.utcnow().replace(microsecond=0)

        self.exchange = exchange_class(advisors, dt_start=self.dt_start)
        self.exchange.on_event = self.on_event

        self.account_stats = AccountStats(self.exchange, target_margin)
        self.trade_stats = TradeStats()

    def warm_up(self):
        cprint("\nHistorical data", "white")
        self.exchange.warm_up()
        self.portfolio_info()

    def start(self):
        cprint("\nStart stream", "white")
        self.account_stats.snapshot()
        self.exchange.start_listen()
        self.stop()

    def stop(self):
        cprint("\nStop stream", "white")
        self.exchange.stop_listen()
        self.account_stats.snapshot()
        self.portfolio_info()

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
        # if dt >= self.dt_start and event not in ["quote", "minute"]:
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

        if event in ["minute"]:
            pass
            # self.portfolio_info()

        if event == "after_trade":
            self.trade_stats.on_trade(dt, symbol, payload)
            self.account_stats.on_trade(symbol, payload)
            self.account_stats.update_pl()
            log_trade_result(log, self.exchange, payload)
            # self.portfolio_info()

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
        Сколько сейчас в портфолио должно быть этой штуки.
        """
        state = 0
        for advisor in self.get_advisors(instrument):
            state += advisor.state.numeric / len(self.advisors)

        if not self.can_short:
            state = max(0, state)

        try:
            return self.state_to_position(instrument, state)
        except TypeError:
            return None

    def state_to_position(self, instrument, state):
        """
        Какому количеству акций соответствует данный state.
        Учесть разный margin для шорта и лонга.
        При state 1 позиция должна давать target margin.
        """
        margin = self.exchange.get_margin_level(state < 0)
        price = self.exchange.get_price(instrument, "mid")
        return int(math.floor(self.target_margin * state / margin / price))

    def get_margin_for_position(self, instrument, position):
        amount = position["amount"]
        price = position["price"]
        # price = self.exchange.get_price(instrument, "mid")
        margin_level = self.exchange.get_margin_level(amount < 0)
        return abs(float(amount)) * float(price) * margin_level if price else None

    def on_trade(self, dt: datetime, symbol, tr_price, volume=None):  # noqa
        """
        Тут торговля, если стратегия дала сигнал.
        """
        # cprint(f"\nON_TRADE {dt} {symbol} {tr_price}", "cyan")

        # Протестировать новую цену (не добавляя в историю).
        # Получить сигналы во все стороны.
        can_buy, can_sell = self.get_signals(symbol, dt, tr_price)

        can_buy = self.state_to_position(symbol, can_buy)
        can_sell = self.state_to_position(symbol, can_sell)

        # Это всё должно быть после тестирования новой цены в get_signals,
        # т.к. используется advisor.state, который должен быть посчитан.
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
            amount, side = min(abs(diff), abs(can_buy)), "buy"
        if diff < 0:
            amount, side = -min(abs(diff), abs(can_sell)), "sell"

        # Рыночная цена по текущему стакану
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
        min_tradable_amount = math.floor(Decimal(100) / Decimal(price))
        min_tradable_amount = max(1, min_tradable_amount)
        return min_tradable_amount

    def get_signals(self, instrument, dt, price):
        """
        Посчитать суммарный объем покупки и продажи,
        который предлагают советники для новой цены
        """
        total_buy, total_sell = 0, 0
        all_adv_len = len(self.advisors)

        for advisor in self.get_advisors(instrument):
            assert advisor.state is not None, f"Empty state: {advisor}"

            current_state = advisor.state.numeric
            signal = advisor.test_price(dt, price)
            state_diff = signal.numeric - current_state

            if signal == Signal.PASS:
                continue

            if state_diff > 0:
                total_buy += abs(state_diff / all_adv_len)

            if state_diff < 0:
                total_sell += abs(state_diff / all_adv_len)

        return total_buy, total_sell

    def portfolio_info(self):
        positions = defaultdict(dict)

        for symbol, value in self.exchange.get_positions().items():
            positions[symbol] = value
            positions[symbol]["advised"] = self.get_advised_position(symbol)

        for advisor in self.get_advisors():
            symbol = advisor.instrument
            if symbol not in positions:
                positions[symbol] = {
                    "advised": self.get_advised_position(symbol),
                    "price": self.exchange.get_price(symbol, "mid"),
                    "amount": 0,
                }
        total_margin_used = 0
        print()
        for symbol, position in sorted(positions.items()):
            if position["advised"] is not None:
                advised = "{0:+0.0f}".format(position["advised"])
                m_used = self.get_margin_for_position(symbol, position)
                total_margin_used += m_used
                m_used = "{0:0.0f}".format(m_used)
                color = "cyan"
            else:
                advised = "-"
                m_used = "-"
                color = "white"
            cprint(
                f"{symbol:<12}"
                f"{position['price']:10.2f}"
                f"{position['amount']:+10.0f}"
                f"{m_used:>10}"
                f"{advised:>10}",
                color,
            )
        cprint(f"Net Value:   {self.exchange.net_value:9.2f}", "blue")
        cprint(f"Margin Used: {total_margin_used:9.2f}", "blue")
        print()
