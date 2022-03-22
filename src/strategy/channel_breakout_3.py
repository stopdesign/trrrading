from dataclasses import dataclass, asdict
from datetime import time
from talipp.indicators import DonchianChannels
from strategy import BaseStrategy, Signal, hint
from data_types import Bar, Trade


@dataclass()
class Bar2(Bar):
    """
    Добавляю индикаторы, которые будут сохранены в файл.
    """
    up: float = None
    dn: float = None


class ChannelBreakout3(BaseStrategy):
    don = None
    padding = 0

    def on_start(self):
        self.padding = self.params.get("padding", 0)
        self.don = DonchianChannels(self.length)

    @hint
    def on_bar(self, bar: Bar) -> Signal:

        skip = False

        # if bar.date.time() < time(hour=14, minute=33):
        #     skip = True
        #
        # if bar.date.time() > time(hour=20, minute=59):
        #     skip = True

        # print(bar.rth, bar.date)

        if not bar.rth:
            skip = True

        if bar.volume == 0:
            skip = True

        if not skip:
            self.don.add_input_value(bar)

        # Класс, сохраняющий индикаторы
        bar = Bar2(**asdict(bar))

        if self.don and not skip:
            bar.up = self.don[-1].ub
            bar.dn = self.don[-1].lb

        self.data.append(bar)

        return Signal.PASS

    @hint
    def on_trade(self, trade: Trade) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data[-1] if self.data else None

        if not bar or not bar.dn:
            return Signal.PASS

        if not bar.rth:
            return Signal.PASS

        if trade.price > bar.up - self.padding:
            return Signal.LONG

        if trade.price < bar.dn + self.padding:
            return Signal.SHORT

        return Signal.PASS
