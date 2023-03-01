from __future__ import annotations
from collections import defaultdict
import math
import pytz
from dataclasses import dataclass, asdict
from datetime import time, datetime, timezone
from talipp.indicators import DonchianChannels, KAMA, EMA
from strategy import BaseStrategy, Signal, hint
from data_types import Bar, Trade
from termcolor import colored 


# Хочу такой класс, который будет на лету собирать
# любые данные в OHLC с заданным таймфреймом и вызывать
# события при появлении нового бара.

"""

"""

# class Bar:
#     date: datetime
#     symbol: str
#     open: Decimal
#     high: Decimal
#     low: Decimal
#     close: Decimal
#     volume: int = None
#     rth: bool = None


# Дискретизация в новый таймфрейм
class Resampler:
    """
    Потоковый ресемплер OHLCV-данных в минутные таймфреймы разной длины
    """

    def __init__(self, timeframe: int) -> None:
        self.timeframe = timeframe
        self.cur_bar_items = []
        self.data = []
        self._cur_bar_idx = 0

    def dt_to_ts(self, dt):
        return int(dt.replace(tzinfo=timezone.utc).timestamp())

    def merge(self, data):
        fields = defaultdict(list)
        for bar in data:
            fields["date"].append(bar.date)
            fields["symbol"].append(bar.symbol)
            fields["open"].append(bar.open)
            fields["high"].append(bar.high)
            fields["low"].append(bar.low)
            fields["close"].append(bar.close)
            fields["volume"].append(bar.volume)
            fields["rth"].append(bar.rth)
        frame_bar = {
            "date": fields["date"][0],
            "symbol": fields["symbol"][0],
            "open": fields["open"][0],
            "high": max(fields["high"]),
            "low": min(fields["low"]),
            "close": fields["close"][-1],
            "volume": sum(fields["volume"]),
            "rth": fields["rth"][0],
        }
        return Bar(**frame_bar)

    def push(self, bar: Bar) -> bool:
        """
        Добавляет очередной интервал.
        Возвращает True, если был закрыт предыдущий интервал.
        """
        bar_idx = math.ceil((self.dt_to_ts(bar.date) + 60) / (self.timeframe * 60))
        closed = self._cur_bar_idx and bar_idx != self._cur_bar_idx
        if closed:
            self.data.append(self.merge(self.cur_bar_items))
            self.cur_bar_items = []
        self.cur_bar_items.append(bar)
        self._cur_bar_idx = bar_idx
        return closed

    @property
    def idx(self) -> int:
        return self._cur_bar_idx

    @property
    def closed_bar(self) -> Bar | None:
        return self.data[-2] if len(self.data) > 1 else None

    @property
    def current_bar(self) -> Bar | None:
        return self.data[-1] if self.data else None


class Brainstorm(BaseStrategy):
    def on_start(self):
        self.length = 23

        self.tf_1 = Resampler(30)
        self.tf_2 = Resampler(10)

        self.padding = 0.03

        self.don = DonchianChannels(self.length)
        self.don_1 = DonchianChannels(3)

        self.ema = EMA(50)

    @hint
    def on_bar(self, bar: Bar) -> Signal:

        use_bar = bar.rth and bar.volume > 0

        if use_bar:
            self.data.append(bar)

            self.ema.add_input_value(bar.close)

            closed = self.tf_1.push(bar)
            if closed:
                if self.tf_1.closed_bar:
                    self.don.add_input_value(self.tf_1.closed_bar)

            closed = self.tf_2.push(bar)
            if closed:
                if self.tf_2.closed_bar:
                    self.don_1.add_input_value(self.tf_2.closed_bar)

        return Signal.PASS

    @hint
    def on_trade(self, trade: Trade) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data[-1] if self.data else None

        # print("ON TRADE", trade.rth, trade.date, trade)

        if not bar or not self.don or not trade.rth:
            return Signal.PASS

        don = self.don[-1]
        don_1 = self.don_1[-1]

        price = trade.price

        dt = trade.date.replace(tzinfo=pytz.utc)
        dt = dt.astimezone(tz=pytz.timezone("US/Eastern"))

        time_from_signal = 999
        psdt = None
        if self.prev_signal_dt:
            time_from_signal = (trade.date - self.prev_signal_dt).total_seconds()
            time_from_signal = int(time_from_signal / 60)

            psdt = self.prev_signal_dt.replace(tzinfo=pytz.utc)
            psdt = psdt.astimezone(tz=pytz.timezone("US/Eastern"))

        # print(dt.time(), self.prev_signal, time_from_signal)

        padding = self.padding

        if not len(self.ema):
            return Signal.PASS

        # Интересно
        if time(10, 0) < dt.time() < time(12, 0):
            padding = -0.3

        if time_from_signal and time_from_signal > 200:
            padding = 0.1

        if time_from_signal < 1:
            return Signal.PASS

        ub = don.ub
        lb = don.lb

        # diff = price - self.ema[-1]

        # if diff > +0.5:
        #     padding += 0.2        
        # if diff < -0.5:
        #     padding += 0.2

        if psdt and time_from_signal < 20 and psdt.time() < time(10, 0) and (ub - lb) > 0.5:
            ub = self.don_1[-1].ub
            lb = self.don_1[-1].lb

        if price > ub - padding and price > lb: # and diff > -0.1:
            # print(f"L: {diff:+0.2f}")
            return Signal.LONG

        if price < lb + padding and price < ub: # and diff < 0.1:
            # print(f"S: {diff:+0.2f}")
            return Signal.SHORT

        return Signal.PASS
