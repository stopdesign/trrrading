import json
import logging
from copy import copy
from dataclasses import asdict
from datetime import datetime, timedelta

import redis
from termcolor import colored

from .exchange import Emulator, Exchange
from .market import DataProvider, PolygonAdapter, TradisAdapter
from .stats import PortfolioStats
from .strategy import all_strategies

log = logging.getLogger("trader")


REDIS_CONF = {
    "decode_responses": True,
    "socket_keepalive": True,
    "socket_timeout": 300,
    "health_check_interval": 3,
}


def date_to_datetime(dt):
    return datetime(dt.year, dt.month, dt.day)


class Trader:
    """
    Есть три режима: live, backtest, replay.
    Реальная торговля идет от now до остановки скрипта.
    Бэктест идет от dt_start до dt_end.
    Replay идет от dt_start до dt_end, но через feed.

    Replay - это как бэктест, только данные поступают событиями через redis.
    """

    data_provider: DataProvider
    strategies: list

    def __init__(self, config, backtest, replay):
        dt_now = datetime.utcnow().replace(microsecond=0)
        txt = f"Init Trader(backtest={backtest}) at {dt_now}"
        log.info(colored(txt, "white"))

        self.config = config
        self.backtest = backtest
        self.replay = replay

        run_config = config["backtest"] if backtest else config["live"]

        self.symbols = sorted(list({c["symbol"] for c in config["strategies"]}))
        self.config_start_end(run_config, warm_up=timedelta(days=10))
        self.config_sources(run_config, config["sources"])

        # Добывает данные, запускает события
        self.data_provider = DataProvider(
            symbols=self.symbols,
            history=self.history_source,  # исторические данные одной кучей
            feed=self.feed_source,  # real-time потоковые данные
            dt_prior=self.dt_prior,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
        )

        # Объект, работающий с ордерами
        if self.backtest or self.replay:
            self.exchange = Emulator(self.on_event)
        else:
            account_uid = run_config.get("account")
            self.exchange = Exchange(self.on_event, account_uid)

        # Инициализация стратегий и список индикаторов
        self.strategies = []
        self.indicators = []
        for cfg in config["strategies"]:
            strategy_class = all_strategies[cfg["strategy"]]
            strategy = strategy_class(exchange=self.exchange, **cfg)
            self.strategies.append(strategy)
            self.indicators += list(strategy.indicators)

        # Прогреть индикторы прогоном исторических данных
        self.data_provider.warm_up()

        # Отметить, что стратегии прогреты.
        # Может, лучше сделать это внутри стратегии?
        for strategy in self.strategies:
            strategy.warmed = True

        self.portfolio_stats = PortfolioStats(self, self.exchange, 100000)

        self.portfolio_stats.portfolio_info()
        # self.portfolio_stats.account_info()

    def on_event(self, event, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        Порядок событий пока хрен знает какой.
        """
        if dt and dt > self.dt_start and not self.backtest:
            # log.info(f"EVENT {event} {symbol} {payload}")
            pass

        if event == "quote":
            # Обновление стакана для инструмента
            self.exchange.on_quote(dt, payload)

            # 4. Запустить обработку ордеров
            self.exchange.process_orders()

        if event == "bar":
            # 1. Добавить bar в хранилище баров
            self.exchange.on_bar(dt, payload)

            # 2. Обновить индикаторы, собрать их новые значения
            for indicator in self.indicators:
                indicator.add_bar(copy(payload))

            # 3. Передать bar в стратегии
            for strategy in self.strategies:
                strategy.on_bar(copy(payload))

            # # 4. Запустить обработку ордеров
            # self.exchange.process_orders()

        # TODO: переименовать в tick
        if event == "trade":
            # 3. Передать trade в стратегии
            for strategy in self.strategies:
                strategy.on_trade(copy(payload))

            # 4. Запустить обработку ордеров
            self.exchange.process_orders()

        # Событие ордера, которое нужно передать в стратегию
        if event == "order":
            # TODO: пробрасывать только в стратегию, которая ордер создала
            for strategy in self.strategies:
                strategy.on_order_event(payload)

        # LIVE: Брокер сообщает об изменении ордера, позиций или аккаунта
        if event == "broker":
            self.exchange.on_broker_update(copy(payload))

        if event in ["hour", "day"]:
            if dt > self.dt_start and self.backtest:
                self.portfolio_stats.snapshot()

    def config_start_end(self, conf, warm_up=timedelta(days=5)):
        if self.backtest:
            self.dt_start = date_to_datetime(conf["dt_start"])
            self.dt_end = date_to_datetime(conf["dt_end"]) + timedelta(1)
        elif self.replay:
            if conf.get("dt_start"):
                self.dt_start = date_to_datetime(conf["dt_start"])
            else:
                self.dt_start = date_to_datetime(datetime.utcnow().date())
            if conf.get("dt_end"):
                self.dt_end = date_to_datetime(conf["dt_end"]) + timedelta(1)
            else:
                self.dt_end = None
        else:
            self.dt_start = datetime.utcnow().replace(microsecond=0)
            self.dt_end = None

        # Сколько данных до старта нужно для прогрева индикаторов.
        # Хорошо бы сделать какую-то автоматизацию выбора интервала.
        self.dt_prior = self.dt_start - warm_up

    def config_sources(self, run_config, sources):
        history = run_config["history"]
        feed = run_config.get("feed")

        history_conf = sources.get(history)

        if not history_conf:
            raise ValueError(f"Bad history source config: {history}")

        if "redis" in history:
            redis_client = redis.Redis(**(REDIS_CONF | history_conf))
            self.history_source = TradisAdapter(redis_client)
        elif "polygon" in history:
            self.history_source = PolygonAdapter(**history_conf)
        else:
            raise ValueError(f"Unknown history source: {history}")

        if self.backtest:
            self.feed_source = None
            return

        feed_conf = sources.get(feed)

        if not feed_conf:
            raise ValueError(f"Bad feed source config: {feed}")

        if "redis" in feed:
            redis_client = redis.Redis(**(REDIS_CONF | feed_conf))
            self.feed_source = TradisAdapter(redis_client)
        elif "polygon" in feed:
            self.feed_source = PolygonAdapter(**feed_conf)
        else:
            raise ValueError(f"Unknown feed source: {feed}")

        log.info(f"History: {self.history_source}")
        log.info(f"Feed: {self.feed_source}")

    def start(self):
        print()
        log.info(colored(" Start ", "green", attrs=["reverse", "bold"]))

        # self.portfolio_stats.snapshot()

        try:
            if self.backtest:
                self.data_provider.backtest()
                # TODO: после завершения бэктеста закрыть все позиции
                # self.close_all()
                self.save_backtest_data()
            else:
                self.data_provider.listen()
        except KeyboardInterrupt:
            print()
        except Exception as e:
            log.exception(e)

        log.info(colored(" Stop ", "red", attrs=["reverse", "bold"]))

        if self.backtest:
            self.portfolio_stats.print_summary()  # RESULTS

    def save_backtest_data(self):
        """
        FIXME: код стал еще более ебаным
        """
        import os

        # создание директории для всяких там результатов бэктеста
        dt = datetime.utcnow()  # server time
        day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        ts = (dt - day).total_seconds()
        dir_name = f"{day:%Y-%m-%d}_{ts:06.0f}/"
        base_dir = os.path.join(os.path.dirname(__file__), "../../res", dir_name)
        base_dir = os.path.abspath(base_dir)
        os.makedirs(base_dir)

        # self.strategy_stats.save_ohlc(path, self.dt_start)

        from datetime import timezone

        def dt_to_ts(dt):
            return int(dt.replace(tzinfo=timezone.utc).timestamp())

        # сохранение баров и индикаторов
        for symbol in self.symbols:
            file_name = f"URA.ARCA_strategy_ohlc.jsonl"
            path = os.path.join(base_dir, file_name)
            txt = ""
            for bar in self.exchange.bars[symbol]:
                if bar.date >= self.dt_start:
                    ts = dt_to_ts(bar.date)
                    last_bar = asdict(bar)
                    last_bar["ts"] = ts
                    last_bar["ind"] = []
                    for ind in self.indicators:
                        last_bar["ind"].append(ind.values_by_ts.get(ts, {}))
                    txt += json.dumps(last_bar, default=str) + "\n"
            with open(path, "w") as f:
                f.write(txt)

        # сохранение сделок и депозита
        self.portfolio_stats.save_events(base_dir)
