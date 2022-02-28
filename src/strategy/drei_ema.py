from talipp.indicators import EMA, RSI
from strategy import BaseStrategy, Signal
from data_types import Bar


class DreiEma(BaseStrategy):

    rsi_top = 65
    rsi_bottom = 35
    rsi_period = 14

    def on_start(self):
        self.fast_ema = EMA(5 * 60)
        self.mid_ema = EMA(8 * 60)
        self.slow_ema = EMA(13 * 60)
        self.rsi = RSI(self.rsi_period)

    def on_bar(self, pandas_ohlc):
        bar = Bar.from_pandas(pandas_ohlc)

        if bar.volume == 0:
            return None

        # часовые закрытия
        prev_bar = self.data[-1] if self.data else None
        if prev_bar and prev_bar.date.hour != bar.date.hour:
            self.rsi.add_input_value(bar.close)

        self.fast_ema.add_input_value(bar.close)
        self.mid_ema.add_input_value(bar.close)
        self.slow_ema.add_input_value(bar.close)

        # Для графика
        bar.up = 1
        bar.dn = 1

        self.data.append(bar)

        return bar

    def test_price(self, price: float) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """

        # Нет значений индикаторов
        if not (self.fast_ema and self.mid_ema and self.slow_ema and self.rsi):
            return Signal.PASS

        fast_ema_val = self.fast_ema[-1]
        mid_ema_val = self.mid_ema[-1]
        slow_ema_val = self.slow_ema[-1]
        rsi_val = self.rsi[-1]

        signal = Signal.PASS

        # крокодил выстроился вверх, покупаем
        if fast_ema_val > mid_ema_val > slow_ema_val:
            signal = Signal.LONG

        # крокодил смотрит вниз
        if fast_ema_val < mid_ema_val < slow_ema_val:
            signal = Signal.SHORT

        # проверяем rsi, чтобы знать что рынок в тренде
        if signal != Signal.PASS:
            if self.rsi_top > rsi_val > self.rsi_bottom:
                # рынок во флэте, не заходим в рынок
                signal = Signal.PASS

        return signal
