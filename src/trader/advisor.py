import logging
import pandas_market_calendars as mcal
from datetime import timedelta, datetime
from strategy import Signal, BaseStrategy, all_strategies

log = logging.getLogger("advisor")


class Advisor:
    """
    Знает последнее рекомендованное направление и может
    менять его на основе торговых сигналов от стратегий.

    Инициализируются на основе исторических данных.

    Знает, можно ли торговать в extra_hours,
    и нужно ли передавать такие данные в стратегию.
    """
    strategy: BaseStrategy

    def __init__(self, symbol, extra_trade=False, extra_data=False, **kwargs):
        self.symbol = symbol
        self.strategy_name = kwargs.pop("strategy")
        self.strategy = all_strategies[self.strategy_name](**kwargs)

        self.extra_trade = bool(extra_trade)
        self.extra_data = bool(extra_data)

        start = datetime.utcnow() - timedelta(days=365 * 5)
        end = datetime.utcnow() + timedelta(days=10)
        self.schedule = self.init_schedule(start, end)

        self.state = None
        self.last_bar_dt = None

    def __str__(self):
        return f"<Advisor symbol={self.symbol} strategy={self.strategy}>"

    @property
    def info(self):
        return (
            f"{self.symbol} "
            f"extra_data={self.extra_data:<1} "
            f"extra_trade={self.extra_trade:<1} "
            f"strategy={self.strategy!r}"
        )

    @property
    def exchange_symbol(self):
        exchange_symbol = self.symbol.split(".")[1]
        exchange_symbol = exchange_symbol.replace("ARCA", "NYSE")
        exchange_symbol = exchange_symbol.replace("NYMEX", "CMES")
        exchange_symbol = exchange_symbol.replace("GLOBEX", "CMES")
        exchange_symbol = exchange_symbol.replace("ECBOT", "CMES")
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
        if not (self.is_main_session(dt) or self.extra_data):
            return
        # Проверить, что bar идет без отрыва от предыдущего
        if self.last_bar_dt and self.is_main_session(dt):
            # Разрыв между барами в пределах одной торговой сессии недопустим.
            if dt.date() == self.last_bar_dt.date():
                diff = dt - self.last_bar_dt
                t0 = self.schedule.get(dt.date())[0]
                if diff != timedelta(minutes=1) and dt != t0:
                    log.warning(f"Bar gap {self.symbol}, {dt}, {self.last_bar_dt}")
        self.last_bar_dt = dt
        # Обновить набор исторических данных
        self.strategy.on_bar(bar)

    def test_price(self, dt, price):
        if not (self.is_main_session(dt) or self.extra_trade):
            return Signal.PASS
        if not self.last_bar_dt:
            return Signal.PASS
        diff = dt - self.last_bar_dt
        t0 = self.schedule.get(dt.date())[0]
        dt_min = dt.replace(second=0, microsecond=0)
        if self.is_main_session(dt) and diff > timedelta(seconds=150) and dt_min != t0:
            # Старый бар допустим, если это первый бар основной сессии.
            # Вне основной сессии непрерывность не проверяется.
            log.warning(f"Old bar {self.symbol}, now: {dt}, bar: {self.last_bar_dt}")
            # return Signal.PASS
        signal = self.strategy.test_price(price)
        if signal in [Signal.SHORT, Signal.LONG, Signal.CLOSE]:
            self.state = signal
        return signal
