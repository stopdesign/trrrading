import json
import logging
import os
from copy import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import redis
from data_types import Bar, Hint, Trade
from django.utils.timezone import make_aware
from main.models import Account, Run
from market import DataProvider, PolygonAdapter, TradisAdapter
from stats import PortfolioStats, StrategyStats
from strategy import Signal, all_strategies
from termcolor import colored

from trader import Exchange, Executor, Portfolio

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
    """

    data_provider: DataProvider = None
    exchange: Exchange = None
    strategies: list = None
    executor: Executor = None
    run: Run = None

    def __init__(self, config, backtest, replay):
        dt_now = datetime.utcnow().replace(microsecond=0)
        txt = f"Init Trader(backtest={backtest}) at {dt_now}"
        log.info(colored(txt, "white"))

        self.backtest = backtest
        self.replay = replay

        run_config = config["backtest"] if backtest else config["live"]
        strategies = config["strategies"]
        sources = config["sources"]

        self.target_margin = Decimal(run_config["target_margin"])

        self.symbols = sorted(list({c["symbol"] for c in strategies}))

        self.init_strategies(strategies)

        self.config_start_end(run_config)

        # Сколько данных до старта нужно для прогрева индикаторов.
        # TODO: Хорошо бы сделать какую-то автоматизацию выбора интервала.
        self.dt_prior = self.dt_start - timedelta(days=20)

        # Инициализация источников данных
        self.config_sources(run_config, sources)

        log.info(f"Start: {self.dt_start}, end: {self.dt_end}")
        log.info(f"History: {self.history_source}, feed: {self.feed_source}")

        # Добывает данные, запускает события
        self.data_provider = DataProvider(
            symbols=self.symbols,
            history=self.history_source,
            feed=self.feed_source,
            dt_prior=self.dt_prior,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
        )

        # Exchange занимается стаканом и ценами
        self.exchange = Exchange()

        # Это нужно до прогрева индикаторов,
        # чтобы сохранились индикаторы в процессе прогрева.
        self.strategy_stats = StrategyStats(self.strategies)

        # Прогреть индикторы прогоном исторических данных.
        # На этом этапе еще нет портфолио, только сигналы и Hint.
        self.data_provider.warm_up()

        self.portfolio = Portfolio(self.exchange, self.strategies, self.target_margin)
        self.strategy_stats.portfolio = self.portfolio

        # Пока решил не открывать ордер по сигналу на старте для бэктеста,
        # потому что не хочу показывать прогревочный период на графике.
        # Для торговли нужно инициализировать позиции по прошлым сигналам,
        # чтобы бот при первой возможности купил-продал нужное.
        if not (self.backtest or self.replay):
            self.init_positions()

        # Инициализируется механизм выставления ордера на бирже
        if not (self.backtest or self.replay):
            account = Account.objects.get(
                uid=run_config["account"],
                username=run_config["username"],
            )
            self.run = Run.objects.create(
                account=account,
                start_dt=make_aware(self.dt_start, timezone=timezone.utc),
                broker_config=json.dumps(run_config, indent=2, default=str),
                strategy_config=json.dumps(strategies, indent=2, default=str),
            )
            self.executor = Executor(self.exchange, self.portfolio, self.run)

        self.portfolio_stats = PortfolioStats(self, self.portfolio, self.target_margin)

        self.portfolio_stats.portfolio_info()
        # self.portfolio_stats.account_info()

    def config_start_end(self, conf):
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

    def init_strategies(self, strategy_conf):
        """
        Инициализация классов стратегий.
        """
        self.strategies = []
        for config in strategy_conf:
            strategy_class = all_strategies[config["strategy"]]
            self.strategies.append(strategy_class(**config))

    def init_positions(self):
        """
        Создаются и применяются Hints по последниму состоянию стратегий,
        чтобы позиции соответствовали сигналам.
        """
        # for strategy in self.strategies:
        #     self.portfolio.set_initial_amount(strategy, Decimal(0))
        hints = []
        for strategy in self.strategies:
            # TODO: Тут нужно добыть цену сигнала
            side = strategy.prev_signal.side
            price = self.exchange.get_price(strategy.symbol, side)
            hint = Hint(
                strategy=strategy,
                signal=strategy.prev_signal,
                signal_dt=strategy.prev_signal_dt,
                signal_price=price,
            )
            hints.append(hint)
        self.portfolio.rebalance(hints)

    def start(self):

        print()
        log.info(colored(" Start ", "green", attrs=["reverse", "bold"]))

        self.portfolio_stats.snapshot()

        if self.backtest:
            self.data_provider.backtest()
            self.close_all()
            self.save_backtest_data()

        else:
            try:
                self.data_provider.listen()
            except KeyboardInterrupt:
                pass
            except Exception as e:
                log.exception(e)

            if not self.replay:
                self.run.finished_at = datetime.now(tz=timezone.utc)
                self.run.save()

        log.info(colored(" Stop ", "red", attrs=["reverse", "bold"]))

        if self.backtest:
            self.portfolio_stats.print_summary()  # RESULTS

    def save_backtest_data(self):
        """
        FIXME: ебаный код какой-то
        """
        dt = datetime.utcnow()  # server time
        day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        ts = (dt - day).total_seconds()
        dir_name = f"{day:%Y-%m-%d}_{ts:06.0f}/"
        path = os.path.join(os.path.dirname(__file__), "../../res", dir_name)
        path = os.path.abspath(path)
        os.makedirs(path)
        self.strategy_stats.save_ohlc(path, self.dt_start)
        self.portfolio_stats.save_events(path)

    def on_event(self, event, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        # if dt > self.dt_start and not self.backtest:
        #     log.info(f"EVENT {event} {symbol} {payload}")

        if event == "bar":
            self.on_bar(dt, symbol, payload)

        if event == "trade":
            self.on_trade(dt, symbol, payload)

        if event == "quote":
            self.exchange.add_quote(dt, symbol, payload)

        if event in ["hour", "day"]:
            if dt > self.dt_start:
                self.portfolio_stats.snapshot()

    def on_bar(self, dt: datetime, symbol, payload: Bar):
        """
        Новый интервал. Обновить данные в стратегиях.
        Получить сигналы, зависящие от интервалов.
        """
        hints = []

        for strategy in self.strategies:
            if strategy.symbol == symbol:
                if signal := strategy.on_bar(copy(payload)):
                    hint = Hint(
                        strategy=strategy,
                        signal=signal,
                        signal_dt=dt,
                        signal_price=payload.close,
                    )
                    hints.append(hint)

                # После добавления нового бара в стратегию происходит
                # сохранение бара с индикаторами и профитом
                # TODO: обработать прерывание торгов и close all
                if strategy.data:  # and dt > self.dt_start:
                    self.strategy_stats.append(strategy, dt)

        # # FIXME: эта штука срезает первый bar в реальной торговле
        # if dt > self.dt_start:
        #     self.process_hints(hints, dt)

    def on_trade(self, dt: datetime, symbol, payload: Trade):
        """
        Новая цена. Обновить данные в стратегиях.
        Получить сигналы, зависящие от сделок.
        """
        hints = []

        for strategy in self.strategies:
            if strategy.symbol == symbol:
                if signal := strategy.on_trade(copy(payload)):
                    hint = Hint(
                        strategy=strategy,
                        signal=signal,
                        signal_dt=dt,
                        signal_price=payload.price,
                    )
                    hints.append(hint)

        if dt > self.dt_start:
            self.process_hints(hints, dt)

    def close_all(self):
        hints = []
        for strategy in self.strategies:
            hint = Hint(
                strategy=strategy,
                signal=Signal.CLOSE,
                signal_dt=self.exchange.dt_last,
                signal_price=Decimal("nan"),
            )
            hints.append(hint)
        self.process_hints(hints, self.exchange.dt_last)

    def process_hints(self, hints, dt):
        """
        Обновить состояние портфолио после получения новых сигналов.
        Применить новое состояние портфолио к торговому аккаунту.
        """
        self.portfolio.rebalance(hints)

        if self.backtest:
            return

        if self.executor:
            self.executor.apply_targets(dt)
