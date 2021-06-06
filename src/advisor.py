from decimal import Decimal
from strategy import ChannelBreakout, Signal


class Advisor:
    """
    Штука, которая знает текущее состояние (из сигнала по историческим данным)
    и может менять его на основе торговых сигналов от стратегий.

    Состояния (без пирамидинга):
    — long
    — none
    — short

    Сигналы:
    — buy
    — none
    — sell

    Состояния инициализируются на основе исторических данных.
    """

    def __init__(self, strategy, length, instrument):
        self.instrument = instrument
        self.state = None
        self.strategy = ChannelBreakout(length=length, min_length=1)

    def __str__(self):
        return f"<Advisor symbol={self.instrument} strategy={self.strategy}>"

    def test_price(self, price):
        signal = self.strategy.test(price)
        if signal in [Signal.SHORT, Signal.LONG]:
            self.state = signal
        return signal
