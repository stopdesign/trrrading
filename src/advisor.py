import pandas_market_calendars as mcal
from datetime import timedelta, datetime
from strategy import Signal, all_strategies
from termcolor import cprint


class Advisor:
    """
    Знает последнее рекомендованное направление и может
    менять его на основе торговых сигналов от стратегий.

    Инициализируются на основе исторических данных.

    Знает, можно ли торговать в extra_hours,
    и нужно ли передавать такие данные в стратегию.
    """

    def __init__(
        self,
        strategy,
        instrument,
        length=10,
        extra_trade=False,
        extra_data=True,
        interval=None,
    ):
        strategy_class = all_strategies[strategy]
        self.strategy = strategy_class(interval=interval, length=length)
        self.instrument = instrument
        self.state = None
        self.strategy_name = strategy
        self.extra_trade = extra_trade

        self.use_extra_data = bool(extra_data)
        self.trade_in_extra_hours = bool(extra_trade)

        self.last_bar_dt = None

        start = datetime.utcnow() - timedelta(days=365 * 5)
        end = datetime.utcnow() + timedelta(days=10)
        self.schedule = self.init_schedule(start, end)

    def __str__(self):
        return f"<Advisor symbol={self.instrument} strategy={self.strategy}>"

    @property
    def exchange_symbol(self):
        exchange_symbol = self.instrument.split(".")[1]
        return exchange_symbol.replace("ARCA", "NYSE")

    def init_schedule(self, start, end):
        """
        Добыть расписание биржи, закешировать по дням.
        """
        by_days = {}
        if self.exchange_symbol == "E":
            cal = mcal.get_calendar("NYSE").schedule(start, end)
            for day, t in sorted(cal.T.to_dict("list").items()):
                t0 = t[0].to_pydatetime().replace(hour=0, minute=0)
                t1 = t[0].to_pydatetime().replace(hour=23, minute=59, second=59)
                by_days[day.date()] = [t0.replace(tzinfo=None), t1.replace(tzinfo=None)]
        else:
            cal = mcal.get_calendar(self.exchange_symbol).schedule(start, end)
            for day, t in sorted(cal.T.to_dict("list").items()):
                t0 = t[0].to_pydatetime()
                t1 = t[1].to_pydatetime()
                by_days[day.date()] = [t0.replace(tzinfo=None), t1.replace(tzinfo=None)]
        return by_days

    def is_main_session(self, dt):
        t0, t1 = self.schedule.get(dt.date(), (None, None))
        return t0 and t1 and t0 < dt < t1

    def on_bar(self, dt, bar):
        # Проверить, что bar идет без отрыва от предыдущего
        if self.last_bar_dt and self.is_main_session(dt):
            diff = dt - self.last_bar_dt
            if diff != timedelta(minutes=1) and dt != self.schedule.get(dt.date()):
                cprint(f"GAP — {diff} — {self.last_bar_dt} — {dt}", "red")
        self.last_bar_dt = dt
        if not (self.is_main_session(dt) or self.use_extra_data):
            return
        # Обновить набор исторических данных
        self.strategy.on_bar(bar)

    def test_price(self, dt, price):
        if not (self.is_main_session(dt) or self.trade_in_extra_hours):
            return Signal.PASS
        signal = self.strategy.test_price(price)
        if signal in [Signal.SHORT, Signal.LONG, Signal.CLOSE]:
            self.state = signal
        return signal
