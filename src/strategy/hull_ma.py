import math
from datetime import time
from talipp.indicators import WMA
from strategy import BaseStrategy, Signal, hint
from data_types import Bar, Trade
from dataclasses import asdict, dataclass


@dataclass()
class Bar2(Bar):
    """
    Добавляю индикаторы, которые будут сохранены в файл.
    """
    n1: float = None
    n2: float = None


class HullMa(BaseStrategy):
    n2ma = None
    nma = None
    nsqrt = None

    def on_start(self):
        n_half = round(self.length / 2)
        n_sqrt = round(math.sqrt(self.length))

        self.n2ma = WMA(n_half)
        self.nma = WMA(self.length)
        self.nsqrt = WMA(n_sqrt)

    @hint
    def on_bar(self, bar: Bar) -> Signal:

        if bar.date.time() < time(hour=14, minute=33):
            return Signal.PASS

        if bar.date.time() >= time(hour=20, minute=59):
            return Signal.PASS

        if bar.volume == 0:
            return Signal.PASS

        # Класс, сохраняющий индикаторы
        bar = Bar2(**asdict(bar))

        if self.data:
            self.n2ma.add_input_value(2 * bar.close)
            self.nma.add_input_value(bar.close)

        if self.n2ma and self.nma:
            diff_1 = self.n2ma[-1] - self.nma[-1]
            self.nsqrt.add_input_value(diff_1)

        if len(self.nsqrt) > 1:
            bar.n1 = self.nsqrt[-1]
            bar.n2 = self.nsqrt[-2]

        self.data.append(bar)

        return Signal.PASS

    @hint
    def on_trade(self, trade: Trade) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data[-1] if self.data else None

        if not bar or not bar.n1:
            return Signal.PASS

        if not bar.rth:
            return Signal.PASS

        # if trade.date.time() < time(hour=14, minute=33):
        #     return Signal.PASS
        #
        # if trade.date.time() >= time(hour=20, minute=59):
        #     return Signal.PASS

        if bar.n1 > bar.n2 + 0.0005:
            return Signal.LONG

        if bar.n1 < bar.n2 - 0.0005:
            return Signal.SHORT

        return Signal.PASS
