import dataclasses
import math
from datetime import timedelta
from data_types import Bar
from strategy import BaseStrategy, Signal
from talipp.indicators import DonchianChannels
from talipp.ohlcv import OHLCV


class Range(BaseStrategy):
    range = 0
    len = 0
    don = None
    padding = 0
    count_bars = False

    def on_start(self):
        self.len = 0
        self.range = self.params.get("range", 1.0)
        self.padding = self.params.get("padding", 0)
        self.count_bars = self.params.get("count_bars", False)
        self.don = DonchianChannels(self.length)

    def calc_channel(self, bar):
        prev = self.data[-1]

        self.don.add_input_value(
            # TODO: сделать метод get_ohlcv
            OHLCV(prev.open, prev.high, prev.low, prev.close, prev.volume)
        )

        if self.don:
            bar.up = self.don[-1].ub
            bar.dn = self.don[-1].lb
        else:
            bar.up = None
            bar.dn = None

    def on_bar(self, pandas_ohlc):
        """
        virtual bars — заполнять все разрывы
        """
        bar = Bar.from_pandas(pandas_ohlc)

        if bar.volume == 0:
            return None

        if not self.data:
            self.data.append(bar)
            return bar

        prices = [bar.open, bar.high, bar.low, bar.close]

        cur = float(self.data[-1].close)
        prices_new = []
        gap = 0
        for price in prices:
            while abs(cur - price) > self.range:
                if price > cur:
                    cur += self.range
                    prices_new.append(cur)
                else:
                    cur -= self.range
                    prices_new.append(cur)
                gap += 1
            prices_new.append(price)

        prices = prices_new

        for i, p in enumerate(prices):
            prev = self.data[-1]
            # Попробовать добавить цену в старый бар.
            # Если это приводит к превышению диапазона — создать новый бар.
            if (prev.high - p <= self.range) and (p - prev.low <= self.range):
                # добавляется норм
                prev.high = max(prev.high, p)
                prev.low = min(prev.low, p)
            else:
                # отформатировать старый бар
                if p > prev.high:
                    prev.close = prev.low + self.range
                if p < prev.low:
                    prev.close = prev.high - self.range
                prev.low = min(prev.low, prev.open, prev.close)
                prev.high = max(prev.high, prev.open, prev.close)
                # создать новый бар на основе старого
                nb = dataclasses.replace(bar, open=p, high=p, low=p, close=p)
                nb.date += timedelta(seconds=i+1)

                # if self.data[-2].high < self.data[-1].low:
                #     print(self.data[-2].date, "GAP UP")
                #
                # if self.data[-2].low > self.data[-1].high:
                #     print(self.data[-2].date, "GAP DOWN")

                if self.count_bars:
                    cnt = int(math.ceil(min(bar.barCount / self.count_bars, 20)))
                else:
                    cnt = 1

                for i in range(cnt):
                    self.calc_channel(nb)
                    self.data.append(nb)

        return self.data[-1]

    def test_price(self, price: float) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data[-1] if self.data else None

        if not bar or not bar.dn:
            return Signal.PASS

        if price > bar.up - self.padding:
            return Signal.LONG

        if price < bar.dn + self.padding:
            return Signal.SHORT

        return Signal.PASS
