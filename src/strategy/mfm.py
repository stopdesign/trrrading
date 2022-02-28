from strategy import BaseStrategy, Signal
from data_types import Bar


class MoneyFlowMultiplier(BaseStrategy):

    data_1h = None

    def on_start(self):
        self.data_1h = []
        self.mfm = []

        self.o = []
        self.h = []
        self.l = []
        self.c = []
        self.checked = False
        self.cnt = 0

    def on_bar(self, pandas_ohlc):
        bar = Bar.from_pandas(pandas_ohlc)

        if bar.volume == 0:
            return None

        prev_bar = self.data[-1] if self.data else None
        if prev_bar:
            if prev_bar.date.hour != bar.date.hour:
                # Добавить интервал в data_1h
                # print(pandas_ohlc)
                ohlc = {
                    "open": self.o[0],
                    "high": max(self.h),
                    "low": min(self.l),
                    "close": self.c[-1],
                }
                self.data_1h.append(ohlc)
                if ohlc["high"] == ohlc["low"]:
                    mfm = 0
                else:
                    mfm = ((ohlc["close"] - ohlc["low"]) - (ohlc["high"] - ohlc["close"])) / (ohlc["high"] - ohlc["low"])

                self.mfm.append(mfm)
                self.o = []
                self.h = []
                self.l = []
                self.c = []
                self.checked = False

        self.o.append(bar.open)
        self.h.append(bar.high)
        self.l.append(bar.low)
        self.c.append(bar.close)

        bar.up = 0
        bar.dn = (self.mfm[-1] if self.mfm else 0) + 43

        self.data.append(bar)

        return bar

    def test_price(self, price: float) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data_1h[-1] if self.data_1h else None

        self.cnt += 1

        if not bar:
            return Signal.PASS

        if self.checked:
            return Signal.PASS

        if len(self.mfm) < 3:
            return Signal.PASS

        self.checked = True

        mfm_1 = self.mfm[-1]
        mfm_2 = self.mfm[-2]
        mfm_3 = self.mfm[-3]

        # Покупаем, когда множитель денежного потока достигает -90,00,
        # а два предыдущих значения выше -90,00.

        # Продаем, когда множитель денежного потока достигает 90,00,
        # а предыдущие два значения ниже 90,00.

        if mfm_1 < -0.9 and (mfm_2 > -0.9) and (mfm_3 > -0.9):
            print(len(self.data), self.cnt)
            return Signal.LONG

        if mfm_1 > 0.9 and (mfm_2 < 0.9) and (mfm_3 < 0.9):
            print(len(self.data), self.cnt)
            return Signal.SHORT

        return Signal.PASS
