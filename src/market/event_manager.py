import logging
from datetime import datetime, timedelta
from typing import Callable

from data_types import Bar, BidAsk, Trade

log = logging.getLogger("data_provider")


class EventManager:
    def __init__(self, on_event: Callable):
        self.on_event = on_event
        self.dt_last = None
        self.quotes = False

        self.prev_bar_dt = datetime(2000, 1, 1)
        self.in_the_gap = True

    # FIXME: сомневаюсь, что это должно быть здесь
    def bar_to_trades(self, bar: Bar) -> list[Trade]:
        """
        Разбивает минутный бар на отдельные сделки со смещением.
        """
        trades = []
        # time_shift = 6  # ломает фильтрацию интервалов по dt < dt_start
        for price in {bar.open, bar.high, bar.low, bar.close}:
            trade = Trade(
                date=bar.date, # + timedelta(seconds=time_shift),
                symbol=bar.symbol,
                price=price,
                rth=bar.rth,
            )
            trades.append(trade)
            # time_shift += 10
        return trades

    def interval_event(self, dt):
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
            elif dt.minute != self.dt_last.minute:
                self.on_event("minute", norm_dt)
        self.dt_last = dt

    def notify(self, payload: dict):
        """
        Преобразование payload в dataclass нужного типа.
        Запуск события через вызов on_event.
        """

        self.interval_event(payload["dt"])

        # Это quote
        if self.quotes and payload.get("av_bid"):
            quote = BidAsk.from_redis_quote(payload)
            self.on_event("quote", quote.date, quote.symbol, quote)

        # Это bar
        elif payload.get("o"):

            if not self.quotes:
                quote = BidAsk.from_redis_trade(payload)
                self.on_event("quote", quote.date, quote.symbol, quote)

            bar = Bar.from_redis(payload)
            bar.rth = payload["rth"]

            bar_time_gap = int((bar.date - self.prev_bar_dt).total_seconds() / 60)
            if bar_time_gap > 1:
                if not self.in_the_gap:
                    log.error(f"Large gap: {bar.date}, {bar_time_gap} min")
                self.in_the_gap = True
            else:
                self.in_the_gap = False

            if bar_time_gap < 0:
                log.error(f"Negative gap: {bar.date}, {bar_time_gap} min")

            self.prev_bar_dt = bar.date

            # for trade in self.bar_to_trades(bar):
            # Теперь bar преобразуется в одну сделку с ценой close
            trade = Trade(
                date=bar.date,
                symbol=bar.symbol,
                price=bar.close,
                rth=bar.rth,
            )
            self.on_event("trade", bar.date, bar.symbol, trade)

            self.on_event("bar", bar.date, bar.symbol, bar)
