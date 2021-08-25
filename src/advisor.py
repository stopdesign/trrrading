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
        extra_data=False,
        interval=None,
        **params,
    ):
        strategy_class = all_strategies[strategy]
        self.strategy = strategy_class(interval=interval, length=length, **params)
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
    def info(self):
        return (
            f"{self.instrument:<9}  "
            f"{self.strategy_name}  "
            f"length={self.strategy.length}  "
            f"padding={self.strategy.padding}  "
            f"extra_data={self.use_extra_data:<1}  "
            f"extra_trade={self.trade_in_extra_hours:<1}  "
        )

    @property
    def exchange_symbol(self):
        exchange_symbol = self.instrument.split(".")[1]
        exchange_symbol = exchange_symbol.replace("ARCA", "NYSE")
        exchange_symbol = exchange_symbol.replace("NYMEX", "CMES")
        return exchange_symbol

    def init_schedule(self, start, end):
        """
        Добыть расписание биржи, закешировать по дням.
        """
        by_days = {}
        cal = mcal.get_calendar(self.exchange_symbol).schedule(start, end)
        for day, t in sorted(cal.T.to_dict("list").items()):
            t0 = t[0].to_pydatetime()
            t1 = t[1].to_pydatetime()
            by_days[day.date()] = [t0.replace(tzinfo=None), t1.replace(tzinfo=None)]
        return by_days

    def is_main_session(self, dt):
        t0, t1 = self.schedule.get(dt.date(), (None, None))
        return t0 and t1 and t0 <= dt < t1

    def on_bar(self, dt, bar):
        if not (self.is_main_session(dt) or self.use_extra_data):
            return
        # Проверить, что bar идет без отрыва от предыдущего
        if self.last_bar_dt and self.is_main_session(dt):
            # Разрыв между барами в пределах одной торговой сессии недопустим.
            if dt.date() == self.last_bar_dt.date():
                diff = dt - self.last_bar_dt
                t0 = self.schedule.get(dt.date())[0]
                if diff != timedelta(minutes=1) and dt != t0:
                    cprint(
                        f" Bar gap {self.instrument},"
                        f" new: {dt},"
                        f" old: {self.last_bar_dt} ",
                        color="red",
                        attrs=["reverse"],
                    )
        self.last_bar_dt = dt
        # Обновить набор исторических данных
        self.strategy.on_bar(bar)

    def test_price(self, dt, price):
        if not (self.is_main_session(dt) or self.trade_in_extra_hours):
            return Signal.PASS
        if not self.last_bar_dt:
            return Signal.PASS
        diff = dt - self.last_bar_dt
        t0 = self.schedule.get(dt.date())[0]
        dt_min = dt.replace(second=0, microsecond=0)
        if self.is_main_session(dt) and diff > timedelta(seconds=150) and dt_min != t0:
            # Старый бар допустим, если это первый бар основной сессии.
            # Вне основной сессии непрерывность не проверяется.
            cprint(
                f" Test price old bar {self.instrument},"
                f" now: {dt},"
                f" bar: {self.last_bar_dt} ",
                color="magenta",
                attrs=["reverse"],
            )
            return Signal.PASS
        signal = self.strategy.test_price(price)
        if signal in [Signal.SHORT, Signal.LONG, Signal.CLOSE]:
            self.state = signal
        return signal
