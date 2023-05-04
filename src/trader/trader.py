import json
import logging
import threading
from copy import copy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import redis
from termcolor import colored

from .exchange import Emulator, Exchange
from .market import DataProvider, PolygonAdapter, TradisAdapter
from .stats import PortfolioStats
from .strategy import all_strategies
from .strategy.base import BaseStrategy

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
    strategies: list[BaseStrategy]

    def __init__(self, config, backtest, replay):
        dt_now = datetime.utcnow().replace(microsecond=0)

        txt = f" Trader(backtest={backtest}) at {dt_now}"
        txt = colored(" Init ", "cyan", attrs=["reverse", "bold"]) + txt
        log.info(txt)

        self.config = config

        # Режим работы
        self.backtest: bool = backtest
        self.replay: bool = replay
        self.live: bool = not (self.replay or self.backtest)

        run_config = config["backtest"] if backtest else config["broker"]

        # Объект, работающий с ордерами
        if self.backtest or self.replay:
            self.exchange = Emulator(self.on_event)
        else:
            account_uid = run_config.get("account")
            redis_config = self.config["redis"]
            redis_client = redis.Redis(**(REDIS_CONF | redis_config))
            log.info(f"Redis PubSub: {redis_config}")
            # TODO: вынести sync_client сюда?
            self.exchange = Exchange(self.on_event, account_uid, redis_client)

        # Инициализация стратегий
        self.strategies = []
        self.data_sources = []
        self.consolidators = []
        self.indicators = []
        for cfg in config["strategies"]:
            cfg["backtest"] = self.backtest
            cfg["replay"] = self.replay
            cfg["live"] = self.live
            klass: type[BaseStrategy] = all_strategies[cfg["strategy"]]
            try:
                strategy = klass(exchange=self.exchange, **cfg)
            except Exception as e:
                log.error(f"Strategy init: {e}")
                raise SystemExit
            self.strategies.append(strategy)
            self.data_sources.extend(strategy.data_sources)
            self.consolidators.extend(strategy.consolidators)
            self.indicators.extend(strategy.indicators)

        # Список всех инструментов, используемых в стратегиях
        self.instruments = list(sorted(set([ds.sid for ds in self.data_sources])))

        # Добавляются нулевые позиции для инструментов
        self.exchange.init_positions(self.instruments)

        self.config_start_end(run_config, warm_up=timedelta(days=15))
        self.config_sources(run_config, config["sources"])

        # Добывает данные, запускает события
        self.data_provider = DataProvider(
            instruments=self.instruments,
            history=self.history_source,  # исторические данные одной кучей
            feed=self.feed_source,  # real-time потоковые данные
            dt_prior=self.dt_prior,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
        )

        print()
        txt = colored(" Warming-up ", "white", "on_green", attrs=["dark"])
        log.info(txt)

        # Прогреть индикторы прогоном исторических данных
        self.data_provider.warm_up()

        # Проверка прогретости индикаторов
        for strategy in self.strategies:
            warmed = True
            for indicator in self.indicators:
                if not indicator.ready:
                    warmed = False
                    log.error(f"Indicator is not ready: {indicator}")
            strategy.set_warmed(warmed)

        self.portfolio_stats = PortfolioStats(self, self.exchange, 100000)

        self.portfolio_stats.portfolio_info()
        # self.portfolio_stats.account_info()

    def on_event(self, event, dt, sid=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        Порядок событий пока хрен знает какой.
        """
        if dt and dt > self.dt_start and not self.backtest and event != "tick":
            log.info(f"EVENT {colored(event, 'red')} {sid} {payload}")
            pass

        if event == "quote":
            # Обновление стакана для инструмента
            self.exchange.on_quote(dt, payload)

            # 4. Запустить обработку ордеров
            self.exchange.process_orders()

        if event == "bar":
            # 1. Добавить bar в хранилище баров
            self.exchange.on_bar(dt, payload)

            # 4. Запустить обработку ордеров
            self.exchange.process_orders()

            # Наполнить источники данных и консолидаторы
            for source in self.data_sources + self.consolidators:
                if source.sid == payload.sid:
                    source.add_bar(copy(payload))

            # Обновить индикаторы, собрать их новые значения
            for indicator in self.indicators:
                if indicator.source.sid == payload.sid:
                    indicator.update_source(dt)

            # Теперь источники данных и консолидаторы могут дернуть события
            for source in self.data_sources + self.consolidators:
                if source.sid == payload.sid:
                    source.trigger_events(event, payload)

            # 4. Запустить обработку ордеров
            self.exchange.process_orders()

        if event == "tick":
            for source in self.data_sources + self.consolidators:
                if source.sid == payload.sid:
                    source.trigger_events(event, payload)

            # 4. Запустить обработку ордеров
            self.exchange.process_orders()

        # # Событие ордера, которое нужно передать в стратегию
        # if event == "order":
        #     # TODO: пробрасывать только в стратегию, которая ордер создала
        #     for strategy in self.strategies:
        #         strategy.on_order_event(payload)

        # LIVE: Брокер сообщает об изменении ордера, позиций или аккаунта
        # Событие приходит в отдельном потоке.
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
            else:
                # Отдельный поток занимается синхронизацией с базой
                t = threading.Thread(
                    target=self.exchange.sync_client.listen,
                    daemon=True,
                    name="SyncThread",
                )
                t.start()
                self.data_provider.listen()
        except KeyboardInterrupt:
            print()
        except Exception as e:
            log.exception(e)

        log.info(colored(" Stop ", "red", attrs=["reverse", "bold"]))

        if self.backtest:
            self.save_backtest_data()
            self.portfolio_stats.print_summary()  # RESULTS

    def save_backtest_data(self):
        """
        - почистить старое
        - создать директорию для результатов
        - для каждой рыночной системы сохранить
            - ohlc и индикаторы
            - сделки
        """
        import os
        import shutil

        base_res_dir = os.path.join(os.path.dirname(__file__), "../../res")
        base_res_dir = os.path.abspath(base_res_dir)

        # Удаление старых результатов
        results = list(sorted(os.listdir(base_res_dir)))
        for old_result in results[:-30]:  # всё, кроме последних N
            path = os.path.join(base_res_dir, old_result)
            shutil.rmtree(path)

        # Создание директории для результатов
        dt = datetime.utcnow().replace(microsecond=0)
        day = dt.replace(hour=0, minute=0, second=0)
        ts = (dt - day).total_seconds()
        dir_name = f"{day:%Y-%m-%d}_{ts:06.0f}/"
        base_dir = os.path.join(base_res_dir, dir_name)
        os.makedirs(base_dir)

        # Параметры стратегии, параметры запуска...
        meta = {
            "dt": str(dt),
            "results": self.portfolio_stats.summary(),
            "strategies": [],
        }

        for strategy in self.strategies:
            res = {
                "name": strategy.name,
                "market_system": strategy.market_system,
                "params": strategy.params._asdict(),
                "data_sources": [],
                "indicators": [],
            }

            for ds in strategy.data_sources:
                res["data_sources"].append(
                    {
                        "type": "Data",
                        "sid": ds.sid,
                        "rth": ds.rth,
                    }
                )

            for ds in strategy.consolidators:
                res["data_sources"].append(
                    {
                        "type": "Consolidator",
                        "sid": ds.sid,
                        "rule": ds.rule,
                    }
                )

            for ind in strategy.indicators:
                res["indicators"].append(
                    {
                        "name": ind.name,
                        "params": ind.kwargs,
                        "chart": ind.chart,
                    }
                )

            meta["strategies"].append(res)

        path = os.path.join(base_dir, "meta.json")
        with open(path, "w") as f:
            meta_json = json.dumps(meta, indent=4, default=str)
            f.write(meta_json.replace(": NaN", ": null"))

        # FIXME: ну какого хуя?
        def dt_to_ts(dt):
            return int(dt.replace(tzinfo=timezone.utc).timestamp())

        # Для графика нужны бары интервалов со сделками
        all_trade_ts = []
        for trade in self.exchange.trades:
            all_trade_ts.append(trade["time"])

        # Cохранение баров и индикаторов
        for strategy in self.strategies:
            ms = strategy.market_system
            sid = strategy.sid
            path = os.path.join(base_dir, f"{ms}-ohlc.jsonl")
            txt = ""
            for bar in self.exchange.bars[sid]:
                if bar.date < self.dt_start:
                    continue
                ts = dt_to_ts(bar.date)
                # FIXME: что с этим делать?
                # Взять настройки из стратегии? А как быть с FUT?
                if not bar.rth:
                    continue
                if not bar.volume and ts not in all_trade_ts:
                    continue
                last_bar = asdict(bar)
                last_bar["ts"] = ts
                last_bar["ind"] = []
                for ind in self.indicators:
                    if ind.source.sid == sid:
                        ind_values = ind.values_by_ts.get(ts, {})
                        last_bar["ind"].append(ind_values)
                txt += json.dumps(last_bar, default=str) + "\n"
            with open(path, "w") as f:
                f.write(txt)

        # Сохранение сделок и депозита
        for strategy in self.strategies:
            ms = strategy.market_system
            path = os.path.join(base_dir, f"{ms}-events.jsonl")
            txt = ""
            for trade in self.exchange.trades:
                if trade["ms"] == ms:
                    txt += json.dumps(trade, default=str) + "\n"
            with open(path, "w") as f:
                f.write(txt)
