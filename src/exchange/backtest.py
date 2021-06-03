import math
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, Optional

import pandas_market_calendars as mcal
from termcolor import cprint

from exchange import BaseExchange
from strategy import Signal
from util import (
    interval_dt,
    print_order_info,
    print_trade_final_info,
    load_from_file,
    parse_quote,
    print_summary,
)


class BacktestExchange(BaseExchange):

    bid: list
    ask: list
    quotes_updated_at: Optional[datetime]
    cash: Decimal
    symbol: str
    spread: Decimal = Decimal("0.02")  # ura "0.005", copx "0.033"
    dt_from: datetime = datetime(2021, 1, 1)

    def __init__(
        self, on_trade: Callable, on_quote: Callable, on_interval: Callable, **params
    ):
        super().__init__(on_trade, on_quote, on_interval, **params)

        self.symbol = params.get("symbol")
        self.cash_initial = Decimal(params.get("cash", 10_000))

        self.bid = []
        self.ask = []
        self.quotes_updated_at = None
        self.cash = self.cash_initial
        self.fee = Decimal("1.00")

        # info
        self.position_open_cash = self.cash
        self.position_open_dt = None
        self.max_potential_cash = Decimal("-Infinity")
        self.max_drawdown = Decimal("-Infinity")

        self.local_max_potential_cash = Decimal("-Infinity")
        self.local_max_drawdown = Decimal("-Infinity")

    def start_listen(self, loop=None):
        quotes_file = f"./data/live-{self.symbol}-quotes-ticks.jsonl"
        trades_file = f"./data/live-{self.symbol}-trades-ticks.jsonl"
        # trades_file = f"./data/live-{self.symbol}-trades-fake.jsonl"

        try:
            quotes = load_from_file(quotes_file, self.dt_from)
        except FileNotFoundError:
            cprint("No quotes data", "red")
            print()
            quotes = []

        trades = load_from_file(trades_file, self.dt_from)

        # Расписание биржи
        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(start_date=self.dt_from, end_date=datetime.utcnow())
        schedule_dict = {}
        for day, t in schedule.T.to_dict("list").items():
            schedule_dict[day.date()] = [t[0].timestamp(), t[1].timestamp()]

        # Разметить нерабочее время
        for trade in trades:
            ts = trade["timestamp"] / 1000
            is_open = False
            if day := schedule_dict.get(datetime.utcfromtimestamp(ts).date()):
                is_open = day[0] <= ts < day[1]
            if not is_open:
                trade["extra"] = True

        # Выкинуть неторговые интервалы
        trades = list(filter(lambda i: not i.get("extra"), trades))

        # Прибавляю N секунд к Quotes, чтобы они запаздывали относительно Trades.
        # Это эмулирует задержку при размещении ордера.
        for quote in quotes:
            quote["timestamp"] += 10_000

        # Combine data and sort by time
        data = sorted(quotes + trades, key=lambda x: x["timestamp"])

        prev_dt = datetime(1900, 1, 1)

        for event in data:
            if "timestamp" not in event:
                continue
            dt = interval_dt(event)

            # TODO: сделать сбор статистики по произвольным интервалам
            if dt.hour != prev_dt.hour:
                if self.position:
                    if self.position == "LONG":
                        price = self.get_price("sell")
                        profit = (price - self.position_open_price) * self.position_size
                    elif self.position == "SHORT":
                        price = self.get_price("buy")
                        profit = (self.position_open_price - price) * self.position_size
                    else:
                        profit = 0
                    position_open_value = self.position_size * self.position_open_price
                    cash = self.cash + position_open_value + profit - self.fee
                else:
                    cash = self.cash

                # print(f"{dt.date()}\t{cash:0.0f}")

                norm_dt = dt.replace(minute=0, second=0, microsecond=0)
                info = {"cash": cash}
                self.on_interval(norm_dt, info)
                # self.update_stats()
                # self.print_final_info()

            if "price" in event:
                if not quotes:
                    self.quotes_updated_at = dt
                    self.fake_quotes_from_trade(event)
                    self.on_quote(event)
                    self.update_stats()
                self.on_trade(event)
            elif "bid" in event and "ask" in event:
                self.ask = list(map(parse_quote, event["ask"]))
                self.bid = list(map(parse_quote, event["bid"]))
                self.quotes_updated_at = dt
                self.on_quote(event)
                self.update_stats()
            else:
                raise ValueError(f"Unknown event type: {event}")
            prev_dt = dt

        if self.position:
            self.close_position(interval_dt(data[-1]))

    def fake_quotes_from_trade(self, trade):
        """
        Фейковый стакан (ask и bid) по сделке.
        """
        event = {
            "ask": [
                {
                    "price": Decimal(trade["price"]) + self.spread,
                    "size": 1000,
                }
            ],
            "bid": [
                {
                    "price": Decimal(trade["price"]) - self.spread,
                    "size": 1000,
                }
            ],
        }
        self.ask = list(map(parse_quote, event["ask"]))
        self.bid = list(map(parse_quote, event["bid"]))

    def update_stats(self):
        # если открыта позиция, посчитать гипотетическую прибыль / убыль
        if self.position:
            if self.position == "LONG":
                price = self.get_price("sell")
                profit = (price - self.position_open_price) * self.position_size
            elif self.position == "SHORT":
                price = self.get_price("buy")
                profit = (self.position_open_price - price) * self.position_size
            else:
                raise ValueError(f"Unknown position type: {self.position}")

            ###############################################
            # глобальные параметры для всей торговли

            position_open_value = self.position_size * self.position_open_price
            # profit_rel = profit / position_open_value * 100
            potential_cash = self.cash + position_open_value + profit - self.fee

            if potential_cash > self.max_potential_cash:
                self.max_potential_cash = potential_cash

            drawdown = self.max_potential_cash - potential_cash
            drawdown_rel = drawdown / position_open_value * 100
            self.max_drawdown = max(self.max_drawdown, drawdown_rel)

            ###############################################
            # локальные параметры для данной сделки

            if potential_cash > self.local_max_potential_cash:
                self.local_max_potential_cash = potential_cash

            local_drawdown = self.local_max_potential_cash - potential_cash
            local_drawdown_rel = local_drawdown / position_open_value * 100
            self.local_max_drawdown = max(self.local_max_drawdown, local_drawdown_rel)

    def get_price(self, side: str) -> Decimal:
        if side == "sell":
            price = self.bid[0]["price"]
        elif side == "buy":
            price = self.ask[0]["price"]
        else:
            raise ValueError(f"Unknown side: {side}")
        return price

    def get_max_amount(self, cash, side):
        price = self.get_price(side)
        return math.floor(cash / price)

    def create_order(self, side: str, size: int):
        price = self.get_price(side)  # bid or ask
        return price, size

    def check_quote_age(self, dt):
        quote_age = (dt - self.quotes_updated_at).total_seconds()
        if quote_age > 300 or quote_age < 0:
            # cprint(f"quote age: {quote_age}", color="cyan")
            return False
        else:
            # cprint(f"quote age: {quote_age}", color="white")
            return True

    def open_position(self, dt: datetime, signal: Signal, size: int):
        if not self.check_quote_age(dt):
            return

        if signal == Signal.LONG:
            size = self.get_max_amount(self.cash, "buy")
            if size <= 0:
                return
            price, _ = self.create_order("buy", size)
        elif signal == Signal.SHORT:
            size = self.get_max_amount(self.cash, "sell")
            if size <= 0:
                return
            price, _ = self.create_order("sell", size)
        else:
            raise ValueError(f"Unknown signal: {signal}")

        self.position_open_cash = self.cash
        self.cash -= price * size + self.fee

        # print_order_info(dt, signal.value, price, size, self.cash)

        self.position = signal.value
        self.position_size = size
        self.position_open_price = price
        self.position_open_dt = dt

    def close_position(self, dt: datetime):
        if not self.check_quote_age(dt):
            return

        if self.position == "LONG":
            price, size = self.create_order("sell", self.position_size)
            profit = (price - self.position_open_price) * self.position_size
        elif self.position == "SHORT":
            price, size = self.create_order("buy", self.position_size)
            profit = (self.position_open_price - price) * self.position_size
        else:
            raise ValueError(f"Unknown position type: {self.position}")

        position_open_value = self.position_size * self.position_open_price
        profit_rel = profit / position_open_value * 100
        self.cash += position_open_value + profit - self.fee

        # print_order_info(dt, "CLOSE", price, 0, self.cash)
        # print()

        # TODO: вынести position(s) в отдельный класс,
        # TODO: перенести в него все параметры о сделке
        # print_trade_final_info(
        #     dt,
        #     self.position,
        #     self.position_open_dt,
        #     profit,
        #     profit_rel,
        #     self.cash,
        #     self.cash_initial,
        #     self.max_potential_cash,
        #     self.max_drawdown,
        #     self.local_max_potential_cash,
        #     self.local_max_drawdown,
        # )
        # print()

        self.position_open_cash = None
        self.position = None
        self.position_size = 0
        self.position_open_price = None

        self.local_max_potential_cash = Decimal("-Infinity")
        self.local_max_drawdown = Decimal("-Infinity")

    def print_final_info(self):
        print()
        print_summary(
            self.position,
            0,
            0,
            self.cash,
            self.cash_initial,
            self.max_drawdown,
            self.local_max_drawdown,
        )
