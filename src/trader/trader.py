import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from termcolor import colored
from data_types import Hint, Bar, Trade
from exchange import BaseExchange, all_exchanges
from stats import AccountStats, TradeStats
from storage.redis import RedisTradingData
from trader import Portfolio, TelegramBotMixin, Execution
from strategy import all_strategies
from main.models import Account, Run

log = logging.getLogger("trader")


class Trader(TelegramBotMixin):
    exchange: BaseExchange = None

    def __init__(self, broker_conf, instruments, backtest):
        dt_now = datetime.utcnow().replace(microsecond=0)
        txt = f"Init Trader(backtest={backtest}) at {dt_now}"
        log.info(colored(txt, "white"))

        self.backtest = backtest

        if self.backtest:
            account = None
        else:
            account = Account.objects.get(
                uid=broker_conf["account"],
                username=broker_conf["username"],
            )

        self.run = Run.objects.create(
            account=account,
            backtest=self.backtest,
            broker_config=json.dumps(broker_conf, indent=2, default=str),
            strategy_config=json.dumps(instruments, indent=2, default=str),
        )

        self.target_margin = broker_conf.get("target_margin")
        self.can_short = broker_conf.get("short", True)
        self.resample_rule = broker_conf.get("resample_rule", None)

        self.instruments = instruments
        self.strategies = []

        # Инициализация стратегий
        for symbol, config in instruments.items():
            for strategy_conf in config["strategies"]:
                strategy_class = all_strategies[strategy_conf["name"]]
                self.strategies.append(strategy_class(symbol, **strategy_conf))

        exchange_class = all_exchanges[broker_conf.get("driver")]

        if self.backtest:
            dt = broker_conf.get("dt_start")
            self.dt_start = datetime(dt.year, dt.month, dt.day)
            dt = broker_conf.get("dt_end")
            self.dt_end = datetime(dt.year, dt.month, dt.day) + timedelta(1)
        else:
            self.dt_start = datetime.utcnow().replace(second=0, microsecond=0)
            self.dt_end = None

        # TODO: инициализировать состояние портфолио?
        self.exchange = exchange_class(
            instruments,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
            backtest=self.backtest,
        )

        self.trading_data = RedisTradingData(
            instruments,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
            backtest=self.backtest,
        )

        self.portfolio = Portfolio(self.exchange)
        self.execution = Execution(self.exchange, self.portfolio, self.run)

        self.init_portfolio()

        self.account_stats = AccountStats(self, self.exchange)
        self.trade_stats = TradeStats(self, self.exchange)

    def init_portfolio(self):
        """
        Инициализировать начальное состояние портфолио.
        Для бэктеста все инструменты из конфига устанавливаются в 0.
        Для торговли берется состояние из базы данных для данного аккаунта.
        Отсутствующие инструменты из конфига устанавливаются в 0.
        """
        for symbol in self.instruments.keys():
            self.exchange.positions[symbol] = {
                "amount": Decimal(0),
                "price": Decimal(0),
            }

    def warm_up(self):
        """
        TODO: Почему не в init?
        """
        log.info(colored(f"Historical data from {self.trading_data.dt_from}", "white"))

        # Прогреть индикторы прогоном исторических данных
        self.trading_data.warm_up()

        self.account_stats.portfolio_info()
        self.account_stats.account_info()

    def start(self):
        self.start_tg_bot()

        log.info("Start stream")
        self.account_stats.snapshot()
        self.trading_data.start_listen()

        log.info("Stop stream")
        self.trading_data.stop_listen()
        self.close_all()
        self.account_stats.snapshot()
        self.account_stats.portfolio_info()
        self.account_stats.account_info()

        self.stop_tg_bot()

    def stop(self):
        self.close_all()
        self.trading_data.stop_listen()

    def final_info(self):
        """
        Завершение торговли (штатное или из-за ошибки).
        Сохранить все наработанные данные.
        """
        if self.backtest:
            self.account_stats.print_summary()  # RESULTS

    def on_event(self, event, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        # if dt >= self.dt_start and not self.backtest:
        #     log.info(f"EVENT {event} {symbol} {payload}")

        if event == "bar":
            self.on_bar(dt, symbol, payload)

        if event == "trade":
            if dt >= self.dt_start:
                self.on_trade(dt, symbol, payload)

        if event == "quote":
            self.exchange.add_quote(dt, symbol, payload)

        if event in ["hour", "day", "after_trade"]:
            if dt >= self.dt_start:
                self.account_stats.snapshot()

        if event in ["minute"]:
            pass

        if event == "after_trade":
            self.trade_stats.on_trade_done(dt, symbol, payload)
            self.account_stats.on_trade_done(symbol, payload)
            self.trade_stats.log_trade_result(symbol, payload)

            # if not self.backtest:
            self.account_stats.portfolio_info()
            self.account_stats.account_info()

        return True

    def on_bar(self, dt: datetime, symbol, payload: Bar):
        """
        Новый интервал. Обновить данные в стратегиях.
        Получить сигналы, зависящие от интервалов.
        """
        hints = []

        # TODO: добавить цену сигнала в hint
        for strategy in self.strategies:
            if strategy.symbol == symbol:
                if signal := strategy.on_bar(payload):
                    hint = Hint(
                        symbol=symbol,
                        strategy=strategy,
                        signal=signal,
                        signal_dt=dt,
                        signal_price=payload.close,
                    )
                    hints.append(hint)

        # self.process_hints(hints, dt)

    def on_trade(self, dt: datetime, symbol, payload: Trade):
        """
        Новая цена. Обновить данные в стратегиях.
        Получить сигналы, зависящие от сделок.
        """
        hints = []

        # TODO: добавить цену сигнала в hint
        for strategy in self.strategies:
            if strategy.symbol == symbol:
                if signal := strategy.on_trade(payload):
                    hint = Hint(
                        symbol=symbol,
                        strategy=strategy,
                        signal=signal,
                        signal_dt=dt,
                        signal_price=payload.price,
                    )
                    hints.append(hint)

        self.process_hints(hints, dt)

    def process_hints(self, hints, dt):
        """
        Обновить состояние портфолио после получения новых сигналов.
        Применить новое состояние портфолио к торговому аккаунту.
        """
        # Обновить Portfolio Targets
        self.portfolio.rebalance(hints)

        # Выставить ордеры, чтобы позиции стали равны Targets
        # Отталкиваться от hints
        self.execution.apply_targets(dt)

    def close_all(self):
        self.portfolio.nullify()
        self.execution.apply_targets(self.exchange.dt_last)
