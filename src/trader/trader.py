import json
import logging
import os
from copy import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from termcolor import colored
from data_types import Hint, Bar, Trade
from stats import PortfolioStats, StrategyStats
from storage import RedisTradingData, Polygon
from trader import Exchange, Portfolio, Executor
from strategy import all_strategies, Signal
from main.models import Account, Run
from django.utils.timezone import make_aware

log = logging.getLogger("trader")


def date_to_datetime(dt):
    return datetime(dt.year, dt.month, dt.day)


class Trader:
    exchange: Exchange = None
    strategies: list = None
    executor: Executor = None

    def __init__(self, broker_conf, strategy_conf, backtest):
        dt_now = datetime.utcnow().replace(microsecond=0)
        txt = f"Init Trader(backtest={backtest}) at {dt_now}"
        log.info(colored(txt, "white"))

        self.backtest = backtest
        self.symbols = sorted(list({c["symbol"] for c in strategy_conf}))
        self.target_margin = Decimal(broker_conf.get("target_margin"))

        self.init_strategies(strategy_conf)

        # У бэктеста есть начало и конец, а реальная
        # торговля идет от now до остановки скрипта
        if self.backtest:
            self.dt_start = date_to_datetime(broker_conf.get("dt_start"))
            self.dt_end = date_to_datetime(broker_conf.get("dt_end")) + timedelta(1)
        else:
            self.dt_start = datetime.utcnow().replace(microsecond=0)
            self.dt_end = None

        # Exchange занимается стаканом и ценами
        self.exchange = Exchange()

        # Добывает данные, запускает события
        self.trading_data = Polygon(
            symbols=self.symbols,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
            backtest=self.backtest,
        )

        # Это нужно до прогрева индикаторов,
        # чтобы сохранились индикаторы в процессе прогрева.
        self.strategy_stats = StrategyStats(self.strategies)

        # Прогреть индикторы прогоном исторических данных.
        # На этом этапе еще нет портфолио, только сигналы и Hint.
        self.trading_data.warm_up()

        self.portfolio = Portfolio(self.exchange, self.strategies, self.target_margin)
        self.strategy_stats.portfolio = self.portfolio

        # Позиции выставляются по прогретым сигналам.
        self.init_positions()

        # Список стратегий, результаты прогрева.
        for strategy in self.strategies:
            amnt = self.portfolio.get_amount(strategy)
            log.info(colored(f"Strategy: {strategy.info} => {amnt}", "grey"))

        # Инициализируется механизм выставления ордера на бирже
        if not self.backtest:
            # TODO: Можно вынести все объекты БД в Executor.
            # TODO: Это границы будущего API с базой.
            account = Account.objects.get(
                uid=broker_conf["account"],
                username=broker_conf["username"],
            )
            self.run = Run.objects.create(
                account=account,
                start_dt=make_aware(self.dt_start),
                broker_config=json.dumps(broker_conf, indent=2, default=str),
                strategy_config=json.dumps(strategy_conf, indent=2, default=str),
            )
            self.executor = Executor(self.exchange, self.portfolio, self.run)

        self.portfolio_stats = PortfolioStats(self, self.portfolio, self.target_margin)

        self.portfolio_stats.portfolio_info()
        # self.portfolio_stats.account_info()

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
            hint = Hint(
                strategy=strategy,
                signal=strategy.prev_signal,
                signal_dt=strategy.prev_signal_dt,
                signal_price=Decimal("nan"),  # TODO: добыть цену
            )
            hints.append(hint)
        self.portfolio.rebalance(hints)

    def start(self):

        log.info(colored(" Start stream ", "green", attrs=["reverse"]))

        self.portfolio_stats.snapshot()

        try:
            # Для бэктеста это заканчивается,
            # для торговли крутится до прерывания
            self.trading_data.start_listen()
        except KeyboardInterrupt:
            self.run.finished_at = datetime.now(tz=timezone.utc)
            self.run.save()
            log.info(colored(" Stop stream ", "red", attrs=["reverse"]))
        except Exception as e:
            log.exception(e)

        if self.backtest:
            self.close_all()
            self.save_backtest_data()
            self.portfolio_stats.print_summary()  # RESULTS

    def save_backtest_data(self):
        dt = datetime.utcnow()  # server time
        day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        ts = (dt - day).total_seconds()
        dir_name = f"{day:%Y-%m-%d}_{ts:06.0f}/"
        path = os.path.join(os.path.dirname(__file__), "../../res", dir_name)
        path = os.path.abspath(path)
        os.makedirs(path)
        self.strategy_stats.save_ohlc(path)
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

        # FIXME: эта штука срезает первый bar в реальной торговле
        if dt > self.dt_start:
            self.process_hints(hints, dt)

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

        self.executor.apply_targets(dt)
