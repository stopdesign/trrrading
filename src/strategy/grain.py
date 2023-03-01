from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from talipp.indicators import DonchianChannels, ATR
from strategy import BaseStrategy, Signal, hint
from data_types import Bar, Trade
from collections import defaultdict
from datetime import timezone

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


@dataclass()
class Bar2(Bar):
    """
    Добавляю индикаторы, которые будут сохранены в файл.
    """
    up: float = None
    dn: float = None


class Grain(BaseStrategy):
    atr = None
    padding = 0.0
    multiplier = 3.0

    def on_start(self):
        self.tf_1 = Resampler(30)

        self.atr = ATR(2)

        self.up = None
        self.dn = None

        self.longStop = [None]
        self.shortStop = [None]

        self.direction = 0

    @hint
    def on_bar(self, bar: Bar) -> Signal:

        use_bar = bar.rth  # and bar.volume > 0

        if use_bar:
            closed = self.tf_1.push(bar)

            if self.tf_1.current_bar:
                cb = self.tf_1.closed_bar
                cur_bar = self.tf_1.current_bar

                if len(self.tf_1.data) > 3:

                    self.atr = ATR(2, self.tf_1.data[-3:])

                    hl2 = (cur_bar.high + cur_bar.low) / 2
                    c_hl2 = (cb.high + cb.low) / 2

                    range = self.atr[-1] * self.multiplier
                    c_range = self.atr[-2] * self.multiplier

                    longStop = hl2 - range
                    longStopPrev = self.longStop[-1] or longStop
                    longStop = max(longStop, longStopPrev) if cb.close > longStopPrev else longStop
                    self.longStop.append(longStop)

                    shortStop = hl2 + range
                    shortStopPrev = self.shortStop[-1] or shortStop
                    shortStop = min(shortStop, shortStopPrev) if cb.close < shortStopPrev else shortStop
                    self.shortStop.append(shortStop)

                    if cur_bar.close > shortStopPrev:
                        self.direction = +1

                    if cur_bar.close < longStopPrev:
                        self.direction = -1

                    self.up = shortStop
                    self.dn = longStop

        # Класс, сохраняющий индикаторы
        bar = Bar2(**asdict(bar))

        bar.up = self.up
        bar.dn = self.dn

        self.data.append(bar)

        return Signal.PASS

    @hint
    def on_trade(self, trade: Trade) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        # bar = self.data[-1] if self.data else None

        # if not bar or not bar.dn:
            # return Signal.PASS

        if self.direction > 0:
            return Signal.LONG
        
        if self.direction < 0:
            return Signal.CLOSE

        # if self.up and trade.price > self.up:
        #     return Signal.LONG

        # if self.dn and trade.price < self.dn:
        #     return Signal.SHORT

        return Signal.PASS
