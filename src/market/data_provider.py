import logging
from collections import defaultdict
from datetime import datetime
from typing import Callable

from market.market_calendar import MarketCalendar
from market.sources.base_source import BaseSource

from .event_manager import EventManager

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
        symbols: list,
        on_event: Callable,
        dt_prior: datetime,
        dt_start: datetime,
        dt_end: datetime,
        history: BaseSource,
        feed: BaseSource = None,
    ):
        self.symbols = symbols

        self.dt_prior = dt_prior
        self.dt_start = dt_start
        self.dt_end = dt_end

        # Инициализация календаря для всех нужных символов и дней
        self.schedule = MarketCalendar(self.symbols, dt_prior, dt_end)

        self.history = history
        self.feed = feed

        self.history.schedule = self.schedule

        # Умеет отправлять сообщения о новых событиях
        self.event_manager = EventManager(on_event)

        self.last_processed_dt = defaultdict(lambda: datetime.min)

    def on_market_event(self, payload):
        """
        Обработка данных из события, передача в event_manager
        """

        # Дополнить payload информацией о расписании биржи
        if "symbol" in payload and "dt" in payload:

            # Проверить, что эти данные новее всех уже обработанных
            dt, symbol = payload["dt"], payload["symbol"]

            if self.last_processed_dt[symbol] >= dt:
                log.warning(f"Interval has been processed: {symbol}, {dt}")
                return

            self.last_processed_dt[symbol] = dt

            payload["rth"] = self.schedule.is_rth(symbol, dt)
            if payload["rth"]:
                self.event_manager.notify(payload)
        else:
            log.warning(f"Unknown payload format: {payload}")

    def warm_up(self):
        """
        Получение исторических данных и запуск
        событий по ним для прогрева индикаторов.
        """

        records = self.history.load(self.symbols, self.dt_prior, self.dt_start)

        log.info(f"warm_up data length: {len(records)}")

        for ts, symbol, payload in records:
            self.on_market_event(payload)

    def backtest(self):
        """ """
        records = self.history.load(self.symbols, self.dt_start, self.dt_end)

        log.info(f"backtest data length: {len(records)}")

        for ts, symbol, payload in records:
            self.on_market_event(payload)

    def listen(self):
        """
        Подписка на real-time данные.
        Запуск событий при получении новых данных.
        """

        if not self.feed:
            raise Exception("No feed source to listen")

        self.feed.listen(self.symbols, self.on_market_event)
