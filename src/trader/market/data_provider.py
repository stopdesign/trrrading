import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable

from .payload_parser import PayloadParser
from .market_calendar import MarketCalendar
from .sources.base_source import BaseSource

log = logging.getLogger("data_provider")


class DataProvider:
    """
    Режимы работы:

    1. Backtest
    Прогрев на исторических данных от dt_0 до dt_1.        warm_up
    Работа на исторических данных от dt_1 до dt_2.         backtest

    2. Live
    Прогрев на исторических данных от dt_0 до dt_1.        warm_up
    Работа на потоковых данных от старта до прерывания.    listen feed

    3. Replay
    Прогрев на исторических данных от dt_0 до dt_1.        warm_up
    Работа на исторических данных от dt_1 до dt_2,         listen feed
    которые подаются в feed, как будто это живые данные.

    """

    def __init__(
        self,
        instruments: list,
        on_event: Callable,
        dt_prior: datetime,
        dt_start: datetime,
        dt_end: datetime | None,
        history: BaseSource,
        feed: BaseSource | None = None,
    ):
        self.instruments = instruments

        self.dt_prior = dt_prior
        self.dt_start = dt_start
        self.dt_end = dt_end
        self.on_event = on_event

        # Инициализация календаря для всех нужных символов и дней
        self.schedule = MarketCalendar(self.instruments, dt_prior, dt_end)

        # Источники данных
        self.history = history
        self.feed = feed

        # Умеет отправлять сообщения о новых событиях
        self.payload_parser = PayloadParser(on_event)

        self.prev_processed_bar_dt = defaultdict(lambda: datetime.min)
        self.in_the_gap: dict = defaultdict(lambda: True)

    def find_prev_not_rth(self, sid, dt) -> datetime | None:
        """
        Ищется интервал, после которого данные должны быть непрерывны.
        Сейчас проверка работает по RTH, но можно сделать как-то иначе.
        """
        cur_dt = dt
        for _ in range(5000):
            cur_dt -= timedelta(minutes=1)
            if not self.schedule.is_rth(sid, cur_dt):
                return cur_dt + timedelta(minutes=1)

    def validate_bar_time(self, payload):
        """
        Проверка правильного порядка интервалов
        и величины промежутков между ними.
        """
        process = True
        sid, dt = payload["sid"], payload["dt"]

        # Bar
        if "o" in payload:
            gap_t1 = self.prev_processed_bar_dt[sid] + timedelta(minutes=1)
            bar_gap = int((dt - gap_t1).total_seconds() / 60)

            if 0 < bar_gap < 10**10:
                prev_min = dt - timedelta(minutes=1)
                if not self.in_the_gap[sid] and self.schedule.is_rth(sid, prev_min):
                    self.in_the_gap[sid] = True
                    gap_t1 = self.find_prev_not_rth(sid, dt) or gap_t1
                    gap_min = int((dt - gap_t1).total_seconds() / 60)
                    log.error(f"Large gap: {sid}, {dt}, {gap_min} min")
            else:
                self.in_the_gap[sid] = False

            # Нарушение последовательности или дублирование
            if self.prev_processed_bar_dt[sid] >= dt:
                log.error(f"Interval has been processed: {sid}, {dt}")
                process = False

            self.prev_processed_bar_dt[sid] = dt

        return process

    def on_market_event(self, payload):
        """
        Обработка данных из события, передача в payload_parser
        """

        if "sid" in payload and "dt" in payload:
            # Дополнить payload информацией о расписании биржи
            payload["rth"] = self.schedule.is_rth(payload["sid"], payload["dt"])

            if not self.validate_bar_time(payload):
                return

            # - парсинг payload различных типов
            # - эмуляция tick и quotes из bar
            # - вызов trader.on_event
            self.payload_parser.notify(payload)
        else:
            log.warning(f"Unknown format: {payload}")

    def warm_up(self):
        """
        Получение исторических данных и запуск
        событий по ним для прогрева индикаторов.
        """

        records = self.history.load(self.instruments, self.dt_prior, self.dt_start)

        log.info(f"warm_up data length: {len(records)}")

        for ts, instrument, payload in records:
            self.on_market_event(payload)

    def backtest(self):
        """ """
        records = self.history.load(self.instruments, self.dt_start, self.dt_end)

        log.info(f"backtest data length: {len(records)}")

        for ts, instrument, payload in records:
            self.on_market_event(payload)

    def replay(self, dt_start, dt_end):
        """
        Заменит warm_up и backtest.
        """
        records = self.history.load(self.instruments, dt_start, dt_end)

        # сбросить проверку
        self.last_processed_dt = defaultdict(lambda: datetime.min)

        log.info(f"replay data length: {len(records)}")

        for ts, instrument, payload in records:
            self.on_market_event(payload)

    def listen(self):
        """
        Подписка на real-time данные.
        Запуск событий при получении новых данных.
        """

        if not self.feed:
            raise Exception("No feed source to listen")

        self.feed.listen(self.instruments, self.on_market_event)
