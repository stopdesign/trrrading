import logging
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Callable

from .event_manager import EventManager
from .market_calendar import MarketCalendar
from .sources.base_source import BaseSource
from ..data_types import Bar

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
        dt_end: datetime|None,
        history: BaseSource,
        feed: BaseSource|None = None,
    ):
        self.symbols = symbols

        self.dt_prior = dt_prior
        self.dt_start = dt_start
        self.dt_end = dt_end
        self.on_event = on_event

        # Инициализация календаря для всех нужных символов и дней
        self.schedule = MarketCalendar(self.symbols, dt_prior, dt_end)

        self.history = history
        self.feed = feed

        self.history.schedule = self.schedule

        # Умеет отправлять сообщения о новых событиях
        self.event_manager = EventManager(on_event)

        self.last_processed_dt = defaultdict(lambda: datetime.min)

    def on_market_event(self, payload, split_bar=False):
        """
        Обработка данных из события, передача в event_manager
        """

        # Дополнить payload информацией о расписании биржи
        if "sid" in payload and "dt" in payload:

            dt, symbol = payload["dt"], payload["sid"]

            is_bar = "o" in payload
            # Для OHLC проверить, что эти данные новее всех уже обработанных
            if is_bar:
                if self.last_processed_dt[symbol] >= dt:
                    log.warning(f"Interval has been processed: {symbol}, {dt}")
                    return
                self.last_processed_dt[symbol] = dt

            payload["rth"] = self.schedule.is_rth(symbol, dt)
            if payload["rth"]:
                if is_bar and split_bar:
                    bar = Bar.from_redis(payload)
                    o, h, l, c = bar.open, bar.high, bar.low, bar.close
                    prices = [o, h, l, c] if (h - o) < (h - l) else [o, l, h, c]
                    #double check t in case bar.date means smth different
                    trades = [deepcopy(payload) | {'price': p, 'dt': bar.date +  timedelta(seconds=t)} for p, t in zip(prices, [1, 20, 40, 60])]
                    for trade_payload in trades:
                        self.event_manager.notify(trade_payload)
                # Формат данных, проверка large gap и вызов Trader.on_event
                self.event_manager.notify(payload)
        else:
            log.warning(f"Unknown format: {payload}")

    def on_broker_event(self, payload):
        self.on_event("broker", dt=datetime.now(), payload=payload)

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
            self.on_market_event(payload, split_bar=True)

    def replay(self, dt_start, dt_end):
        """
        Заменит warm_up и backtest.
        """
        records = self.history.load(self.symbols, dt_start, dt_end)

        # сбросить проверку
        self.last_processed_dt = defaultdict(lambda: datetime.min)

        log.info(f"replay data length: {len(records)}")

        for ts, symbol, payload in records:
            self.on_market_event(payload)


    def listen(self):
        """
        Подписка на real-time данные.
        Запуск событий при получении новых данных.
        """

        if not self.feed:
            raise Exception("No feed source to listen")

        self.feed.listen(self.symbols, self.on_market_event, self.on_broker_event)
