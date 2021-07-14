import json
import math
from talipp.indicators import EMA, ATR, DonchianChannels
from collections import defaultdict, namedtuple
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from strategy import BaseStrategy, Signal
from util import trades_to_ohlc, interval_dt, unix_timestamp
from termcolor import cprint

# TODO: dataclass
OHLC = namedtuple("OHLC", "timestamp, interval, open, high, low, close")


class ChannelBreakout2(BaseStrategy):

    def __init__(self, **params):
        super().__init__()

        self.historical = []
        self.historical_short = []
        self.current_bar_data = []
        self.current_bar_interval = None

        self.length = params.pop("length")
        self.interval_size = 1 * 60
        self.indicator = {}

        self.don = DonchianChannels(period=self.length, input_values=[])

        self.indicator_data = []

        self.delta = timedelta(minutes=0)
        self.step = timedelta(seconds=self.interval_size)

        self.state_cash = {}

    def __str__(self):
        return f"<{self.__class__.__name__} length={self.length}>"

    def merge_trades(self) -> dict:
        """
        Конвертер формата: list of trades >> OHLC
        """
        dt = datetime.strptime(self.current_bar_interval, '%Y-%m-%d %H:%M:%S')
        prices = [float(t["price"]) for t in self.current_bar_data]
        res = {
            "timestamp": unix_timestamp(dt, micro=True),
            "interval": self.current_bar_interval,
            "open": prices[0],
            "low": min(prices),
            "close": prices[-1],
            "high": max(prices),
        }
        return res

    def update_trades(self, trade: dict) -> None:
        """
        Добавить новые сделки к историческим данным.
        """
        interval_id = self.get_interval_id(trade)

        if interval_id == self.current_bar_interval:
            # добавить данные в текущий интервал
            self.current_bar_data.append(trade)
            return

        if self.historical_short and self.historical_short[-1]["interval"] == interval_id:
            raise ValueError("Interval has been closed")

        if not self.current_bar_interval or interval_id > self.current_bar_interval:
            # смержить текущий бар и добавить его в историю
            if self.current_bar_interval:
                new_closed_bar = self.merge_trades()
                self.historical_short.append(new_closed_bar)
                self.increment(new_closed_bar)
            # обнулить текущий бар
            self.current_bar_interval = interval_id
            self.current_bar_data = [trade]
        else:
            raise ValueError("Interval is in the past")

    def get_interval_id(self, trade):
        dt = interval_dt(trade)
        dt_cor = dt + self.delta

        # datetime_floor
        interval_time = dt_cor - (dt_cor - datetime.min) % self.step - self.delta

        return f"{interval_time:%Y-%m-%d %H:%M:%S}"

    def increment(self, bar):

        self.don.add_input_value(OHLC(**bar))

        don = self.don[-1] if self.don else None

        if don:
            bar["up"] = don.ub
            bar["dn"] = don.lb
        else:
            bar["up"] = None
            bar["dn"] = None

        # print(json.dumps(bar, indent=2, default=str))

        ######
        # Индикаторы
        bar["timestamp"] = datetime.utcfromtimestamp(bar["timestamp"] / 1000)
        self.indicator_data.append(bar)
        self.historical.append(bar)

    def test_price(self, dt: datetime, price: Decimal) -> Signal:
        """
        Проверить сигнал стратегии после регистрации сделки.
        """
        signal = Signal.PASS

        if not self.indicator_data:
            return signal

        bar = self.indicator_data[-1]

        # Это стратегия
        if bar["up"] and bar["dn"]:
            if price < bar["dn"]:
                signal = Signal.SHORT
            elif price > bar["up"]:
                signal = Signal.LONG

        # if bar["sig_up"]:
        #     signal = Signal.LONG
        #
        # elif bar["sig_dn"]:
        #     signal = Signal.SHORT

        # if signal.value:
        #     txt = f"{dt:%Y-%m-%d %H:%M:%S} "
        #     txt += colored(f" Price: {price:0.4f} ", attrs=["reverse"])
        #     txt += f"Len: {len(self.historical)} • "
        #     txt += colored(f"{signal.value}", signal.color)
        #     print(txt)

        return signal
