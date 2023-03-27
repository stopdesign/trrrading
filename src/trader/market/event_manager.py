import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

from trader.data_types import Bar, BidAsk, Trade

log = logging.getLogger("event_manager")


def parse_dt(dt: str) -> datetime:
    if "." not in dt:
        dt += ".000000"
    return datetime.strptime(dt, "%Y-%m-%d %H:%M:%S.%f")


class EventManager:
    """
    Служебный класс для DataProvider.
    Преобразует данные из dict в dataclass разных типов.
    Следит за Large gap. Разбивает событие bar на разные сделки.
    """

    def __init__(self, on_event: Callable):
        self.on_event = on_event
        self.dt_last = None
        self.quotes = False  # в данных есть quotes

        self.prev_bar_dt = datetime.min
        self.in_the_gap = True

    # FIXME: сомневаюсь, что это должно быть здесь
    def bar_to_trades(self, bar: Bar) -> list[Trade]:
        """
        Разбивает минутный бар на отдельные сделки со смещением.
        """
        trades = []
        time_shift = 6  # ломает фильтрацию интервалов по dt < dt_start
        for price in {bar.open, bar.high, bar.low, bar.close}:
            trade = Trade(
                date=bar.date + timedelta(seconds=time_shift),
                sid=bar.sid,
                price=price,
                rth=bar.rth,
            )
            trades.append(trade)
            time_shift += 10
        return trades

    def interval_event(self, dt: datetime):
        """
        Запустить интервальное событие при необходимости.
        """
        if self.dt_last and dt.minute != self.dt_last.minute:
            norm_dt = dt.replace(second=0, microsecond=0)
            if dt.day != self.dt_last.day:
                norm_dt = norm_dt.replace(hour=0, minute=0)
                self.on_event("day", norm_dt)
            elif dt.hour != self.dt_last.hour:
                norm_dt = norm_dt.replace(minute=0)
                self.on_event("hour", norm_dt)
            # elif dt.minute != self.dt_last.minute:
            #     self.on_event("minute", norm_dt)
        self.dt_last = dt

    def validate_bar_time(self, bar: Bar):
        """
        Проверка соблюдения последовательности
        интервалов и промежутков между интервалами.
        """
        # FIXME: убрать хардкодинг допустимых интервалов
        valid_gap = [1050, 1150, 3870, 3930, 4030, 5370, 5470]

        # FIXME: тут нужна поддержка разных инструментов
        bar_gap = int((bar.date - self.prev_bar_dt).total_seconds() / 60) - 1
        if bar_gap > 0:
            if not self.in_the_gap and bar_gap not in valid_gap:
                log.error(f"Large gap: {bar.date}, {bar_gap} min")
            self.in_the_gap = True
        else:
            self.in_the_gap = False

        # FIXME: поставить 0, когда будет поддержка разных инструментов
        if bar_gap < -1:
            log.error(f"Negative gap: {bar.date}, {bar_gap} min")

        self.prev_bar_dt = bar.date

    def notify(self, payload: dict):
        """
        Преобразование payload в dataclass нужного типа.
        Запуск события через вызов on_event.
        """

        self.interval_event(payload["dt"])

        # Это quote bar
        if self.quotes and payload.get("av_bid"):
            quote = BidAsk.from_redis_quote(payload)
            self.on_event("quote", quote.date, quote.sid, quote)

        # Это tick
        elif payload.get("price"):
            dt = payload["dt"]
            sid = payload["sid"]
            trade = Trade(
                date=dt,
                sid=sid,
                price=Decimal(payload["price"]),
            )
            self.on_event("tick", dt, sid, trade)

        # Это trade bar
        elif payload.get("o"):
            # Симуляция quote из trade bar
            if not self.quotes:
                quote = BidAsk.from_redis_trade(payload)
                self.on_event("quote", quote.date, quote.sid, quote)

            bar = Bar.from_redis(payload)

            self.validate_bar_time(bar)

            # # Эмуляция отдельных сделок по границам OHLC-бара
            # for trade in self.bar_to_trades(bar):
            #     trade = Trade(
            #         date=trade.date,
            #         sid=trade.sid,
            #         price=trade.price,
            #         rth=trade.rth,
            #     )
            #     self.on_event("tick", bar.date, bar.sid, trade)

            # Теперь bar преобразуется в одну сделку с ценой close
            trade = Trade(
                date=bar.date,
                sid=bar.sid,
                price=bar.close,
                rth=bar.rth,
            )
            self.on_event("tick", bar.date, bar.sid, trade)

            self.on_event("bar", bar.date, bar.sid, bar)
