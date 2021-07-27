import json  # noqa
import logging
import math
import pandas as pd
from datetime import datetime
from decimal import Decimal
from termcolor import cprint, colored
from exchange import BaseExchange, all_exchanges
from notifications.alert import send_telegram  # noqa
from stats import AccountStats, TradeStats
from strategy import Signal
from settings import CAN_SHORT


CURSOR_UP_ONE = "\x1b[1A"
ERASE_LINE = "\x1b[2K"


log = logging.getLogger("trader")
logging.basicConfig(level=logging.DEBUG, format='%(message)s')


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
        cprint("Historical data", "white")
        self.exchange.warm_up()

    def start(self, loop=None):
        cprint("Start stream", "white")
        self.account_stats.snapshot()
        self.exchange.start_listen()

    def stop(self, loop=None):  # noqa
        cprint("Stop stream", "white")
        self.exchange.stop_listen()
        self.account_stats.snapshot()

    def final_info(self):
        with open("data.csv", "w") as d:
            df = pd.DataFrame(self.get_advisors()[0].strategy.data)
            df.set_index("date", inplace=True)
            df = df.loc[self.dt_start:]
            df.to_csv(d)

        self.trade_stats.to_csv("trades.csv")

        self.account_stats.to_csv("stats.csv")
        self.account_stats.print_summary()

    def on_event(self, event, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        # cprint(f"{dt}: EVENT {event} {symbol}", "white")

        if event == "bar":
            for advisor in self.get_advisors(symbol):
                advisor.strategy.on_bar(payload)

        if event == "trade" and dt < self.dt_start:
            for advisor in self.get_advisors(symbol):
                advisor.strategy.test_price(payload.price)

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

        return True

    def get_advisors(self, symbol=None):
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

    def on_trade(self, dt: datetime, instrument, trigger_price, volume=None):  # noqa
        """
        Тут торговля, если стратегия дала сигнал.
        Здесь же риск-менеджмент уровня аккаунта,
        контроль использования маржи.
        """
        # cprint(f"\nON_TRADE {dt} {instrument} {trade_price}", "cyan")
        # self.portfolio_info()

        # Протестировать новую цену (не добавляя в историю).
        # Получить суммарный объем на покупку/продажу по всем сигналам.
        total_buy, total_sell = self.test_new_price(instrument, dt, trigger_price)

        # Это всё должно быть после тестирования новой цены // TODO: почему?
        current_position = self.get_current_position(instrument)
        advised_position = self.get_advised_position(instrument)

        diff = advised_position - current_position

        # Всё равно ничего сделать нельзя
        if not (diff and (total_buy or total_sell)):
            # cprint(f"SKIP: diff: {diff}, buy: {total_buy}, sell: {total_sell}")
            return

        # Посчитать, куда нужно торговать.
        # Скоректировать объем по возможностям, которые есть по сигналам.
        asset_amount_diff, side = 0, None
        if diff > 0:
            asset_amount_diff, side = min(abs(diff), total_buy), "buy"
        if diff < 0:
            asset_amount_diff, side = min(abs(diff), total_sell), "sell"

        price = self.exchange.get_price(instrument, side)

        # Предлагаемое изменение должно быть больше минимального
        if asset_amount_diff < self.get_min_tradable_amount(price):
            asset_amount_diff, side = 0, None

        self.log_trade(
            dt, side, instrument, trigger_price, price, current_position,
            advised_position, asset_amount_diff, total_sell, total_buy
        )

        # Если есть все параметры — запустить сделку
        if price and side and asset_amount_diff:
            self.exchange.trade(side, asset_amount_diff, instrument, dt)

    def log_trade(self, dt, side, symbol, trigger_price, market_price, current_position,
                  advised_position, amount_diff, total_sell, total_buy):
        symbol_str = colored(f"{symbol:>10}", attrs=["bold"])
        color, sign = "cyan", "*** "
        if side == "buy":
            color, sign = "green", "+"
        if side == "sell":
            color, sign = "red", "-"
        action = colored(f"{(sign + str(amount_diff)):>5}", color)
        price_diff = abs(trigger_price - market_price) / market_price * 100
        txt = (
            f"{dt:%Y-%m-%d %H:%M:%S}  {symbol_str}    "
            f"cur/adv: {current_position:+6.0f} {advised_position:+6.0f}    "
            f"signal: {total_buy:+5.0f} {-total_sell:+5.0f}    "
            f"do: {action}    𝝙: {price_diff:0.2f}"
        )
        txt = txt.replace("+0", colored(" 0", "white"))
        log.info(txt)
        # send_telegram(txt)

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
