import pandas_market_calendars as mcal
from datetime import timedelta, datetime, timezone
from strategy import Signal, all_strategies
from util import interval_dt


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
        extra_hours=False,
        extra_hours_data=True,
        interval=None,
    ):
        strategy_class = all_strategies[strategy]
        self.strategy = strategy_class(interval=interval, length=length)
        self.instrument = instrument
        self.state = None
        self.strategy_name = strategy
        self.extra_hours = extra_hours

        self.use_extra_hours_data = bool(extra_hours_data)
        self.trade_in_extra_hours = bool(extra_hours)

        start = datetime.utcnow() - timedelta(days=365 * 5)
        end = datetime.utcnow() + timedelta(days=365)
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
                by_days[day.date()] = [t0, t1]
        else:
            cal = mcal.get_calendar(self.exchange_symbol).schedule(start, end)
            for day, t in sorted(cal.T.to_dict("list").items()):
                by_days[day.date()] = [t[0].to_pydatetime(), t[1].to_pydatetime()]
        return by_days

    def is_main_session(self, dt):
        dt = dt.astimezone(timezone.utc)
        t0, t1 = self.schedule.get(dt.date(), (None, None))
        return t0 and t1 and t0 < dt < t1

    def update_strategy(self, trade):
        dt = interval_dt(trade)
        if not (self.is_main_session(dt) or self.use_extra_hours_data):
            return
        # Обновить текущий внутренний state стратегии
        self.test_price(interval_dt(trade), trade["price"])
        # Обновить набор исторических данных
        self.strategy.update_trades(trade)

    def test_price(self, dt, price):
        if not (self.is_main_session(dt) or self.trade_in_extra_hours):
            return Signal.PASS
        signal = self.strategy.test_price(dt, price)
        if signal in [Signal.SHORT, Signal.LONG, Signal.CLOSE]:
            self.state = signal
        return signal
