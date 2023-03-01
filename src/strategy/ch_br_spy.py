import pytz
from dataclasses import dataclass, asdict
from talipp.indicators import DonchianChannels
from strategy import BaseStrategy, Signal, hint
from data_types import Bar, Trade


"""
Попытка ориентироваться на индекс при принятии решений.
"""


@dataclass()
class Bar2(Bar):
    """
    Добавляю индикаторы, которые будут сохранены в файл.
    """
    up: float = None
    dn: float = None


class ChBrSpy(BaseStrategy):
    don = None
    padding = 0

    def on_start(self):
        # self.padding = self.params.get("padding", self.padding)
        self.padding = getattr(self.params, "padding", self.padding)
        self.don = DonchianChannels(self.length)
        self.don_spy = DonchianChannels(10)
        self.spy = []

    @hint
    def on_bar(self, bar: Bar) -> Signal:

        skip = False

        if not bar.rth:
            skip = True

        if bar.volume == 0:
            skip = True

        if bar.symbol == "SPY.ARCA":

            if not skip:
                self.don_spy.add_input_value(bar)
            
            self.spy.append(bar)

        if bar.symbol == self.symbol:

            if not skip:
                self.don.add_input_value(bar)

            # Класс, сохраняющий индикаторы
            bar = Bar2(**asdict(bar))

            if self.don and not skip:
                bar.up = self.don[-1].ub
                bar.dn = self.don[-1].lb
            else:
                # ETH бары используют последний добавленный RTH интервал
                if self.data and bar.rth:
                    bar.up = self.data[-1].up
                    bar.dn = self.data[-1].dn

            self.data.append(bar)

        return Signal.PASS

    @hint
    def on_trade(self, trade: Trade) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data[-1] if self.data else None

        dt = trade.date.replace(tzinfo=pytz.utc)
        dt = dt.astimezone(tz=pytz.timezone("US/Eastern"))

        if not bar or not bar.dn:
            return Signal.PASS

        if not (trade.rth and bar.rth):
            return Signal.PASS
        
        print(self.spy[-1], self.data[-1])

        if trade.price > bar.up - self.padding:
            return Signal.LONG

        if trade.price < bar.dn + self.padding:
            return Signal.SHORT

        return Signal.PASS
