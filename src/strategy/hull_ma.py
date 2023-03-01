import math
from datetime import time, datetime
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

    padding = 0.0
    timeframe = 30
    
    tf_bar_date = datetime(2000, 1, 1)

    def on_start(self):
        self.padding = getattr(self.params, "padding", self.padding)
        self.timeframe = getattr(self.params, "timeframe", self.timeframe)
        
        n_half = round(self.length / 2)
        n_sqrt = round(math.sqrt(self.length))

        self.n2ma = WMA(n_half)
        self.nma = WMA(self.length)
        self.nsqrt = WMA(n_sqrt)

    @hint
    def on_bar(self, bar: Bar) -> Signal:

        if bar.volume == 0:
            return Signal.PASS

        # Класс, сохраняющий индикаторы
        bar = Bar2(**asdict(bar))

        if self.data and bar.rth:
            bar_cnt = False
            # bar_cnt = len(self.data) % self.tf == 0

            # is_tf = False
            is_tf = bar.date.minute % self.timeframe == 0

            timeout = False
            if (bar.date - self.tf_bar_date).total_seconds() > self.timeframe * 60:
                timeout = True

            # докинуть данных
            if is_tf or timeout or bar_cnt:
                self.tf_bar_date = bar.date

                self.n2ma.add_input_value(2 * bar.close)
                self.nma.add_input_value(bar.close)

                if self.n2ma and self.nma:
                    diff = self.n2ma[-1] - self.nma[-1]
                    self.nsqrt.add_input_value(diff)

        # записать индикаторы в bar
        if len(self.nsqrt) > 2:
            bar.n1 = self.nsqrt[-1]
            bar.n2 = self.nsqrt[-3]

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

        if not (trade.rth and bar.rth):
            return Signal.PASS

        price_delta = 0

        if bar.n1 > bar.n2 + self.padding and trade.price > bar.n1 + price_delta:
            return Signal.LONG

        if bar.n1 < bar.n2 - self.padding and trade.price < bar.n2 - price_delta:
            return Signal.SHORT if self.params.short else Signal.CLOSE

        return Signal.PASS
