"""

Стратегия.

Есть файл, где лежать предсказания оптимальной цены.
Если цена открытия на 1% больше — продать; на 1% меньше — купить.
Закрыть в районе оптимума.
Стоп на 1.5%, например, для начала.


Как улучшить существующую стратегию.
Если цена открытия на 1% больше оптимума, то сигнал стратегии подавляется.
Если через 5 минут ситуация не изменилась, то стратегия срабатывает.
Как-то так.


"""
from dataclasses import asdict, dataclass
from datetime import datetime, time

import pytz
from talipp.indicators import DonchianChannels

from data_types import Bar, Trade
from strategy import BaseStrategy, Signal, hint


@dataclass()
class Bar2(Bar):
    """
    Добавляю индикаторы, которые будут сохранены в файл.
    """
    up: float = None
    dn: float = None
    op: float = None


class OpenSpike(BaseStrategy):
    don = None
    padding = 0

    def on_start(self):

        self.prev_signal_1 = Signal.PASS

        self.padding = getattr(self.params, "padding", self.padding)
        self.don = DonchianChannels(self.length)
        
        # Загрузить файл с предсказаниями цен.
        symbol = self.symbol.split(".")[0].lower()
        f = open(f"../data/open_target_{symbol}_1.csv")
        res = {}
        for day in f.readlines()[1:]:
            date, price, _ = day.strip().split(",")[:3]
            # date, _, price = day.strip().split(",")[:3]
            date = datetime.strptime(date, '%Y-%m-%d').date()
            price = float(price)
            res[date] = price
        self.optimal_open_prices = res

        # Дни, когда торговля уже произошла.
        self.day_traded = []

        self.time_to_close = time(hour=9, minute=55)
        self.open_time_limit = time(hour=9, minute=35)

    @hint
    def on_bar(self, bar: Bar) -> Signal:

        skip = False

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
        else:
            if self.data and bar.rth:
                bar.up = self.data[-1].up
                bar.dn = self.data[-1].dn

        dt = bar.date.replace(tzinfo=pytz.utc)
        dt = dt.astimezone(tz=pytz.timezone("US/Eastern"))
        bar.op = self.optimal_open_prices.get(dt.date())

        self.data.append(bar)

        return Signal.PASS

    @hint
    def on_trade(self, trade: Trade) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        dt = trade.date.replace(tzinfo=pytz.utc)
        dt = dt.astimezone(tz=pytz.timezone("US/Eastern"))
        
        if dt.time() > self.time_to_close:
            return Signal.CLOSE

        price = trade.price

        day = dt.date()

        optimal = self.optimal_open_prices.get(day)

        if not optimal:
            print("NO PREDICTION", dt)
            return Signal.PASS 

        diff = (price - optimal) / optimal * 100

        limit_1 = 0.6
        limit_2 = 1.4

        if dt.time() > self.open_time_limit:
            return Signal.PASS

        if abs(diff) > 2.5:
            return Signal.CLOSE

        # Не открывать сделку,
        # если в этот день были сигналы
        if day in self.day_traded:
            return Signal.PASS
        
        if diff > +limit_1:
            self.day_traded.append(day)
            if diff > +limit_2:
                return Signal.PASS
            else:
                self.day_traded.append(day)
                return Signal.SHORT
        
        elif diff < -limit_1:
            self.day_traded.append(day)
            if diff < -limit_2:
                return Signal.PASS
            else:
                self.day_traded.append(day)
                return Signal.LONG 
        
        else:
            pass
            self.day_traded.append(day)

        return Signal.PASS
