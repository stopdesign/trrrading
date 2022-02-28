import logging
import pandas as pd
from datetime import datetime
from termcolor import colored
from exchange import BaseExchange, all_exchanges
from stats import AccountStats, TradeStats
from storage.redis import RedisTradingData
from trader import Portfolio, TelegramBotMixin, Execution
from strategy import all_strategies

log = logging.getLogger("trader")


class Trader(TelegramBotMixin):
    exchange: BaseExchange = None

    def __init__(self, broker_conf, instruments, base_dir, run):
        txt = f"Init trader at {datetime.utcnow().replace(microsecond=0)} UTC"
        log.info(colored(txt, "white"))

        self.base_dir = base_dir
        self.run = run

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

        if exchange_class.backtest:
            dt = broker_conf.get("dt_start")
            self.dt_start = datetime(dt.year, dt.month, dt.day)
            dt = broker_conf.get("dt_end")
            self.dt_end = datetime(dt.year, dt.month, dt.day)
        else:
            self.dt_start = datetime.utcnow().replace(second=0, microsecond=0)
            self.dt_end = None

        # TODO: инициализировать состояние портфолио?
        self.exchange = exchange_class(
            instruments,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
        )

        self.trading_data = RedisTradingData(
            instruments,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
        )

        self.portfolio = Portfolio(self.exchange)
        self.execution = Execution(self.exchange, self.portfolio)

        self.account_stats = AccountStats(self, self.exchange)
        self.trade_stats = TradeStats(self, self.exchange)

    def warm_up(self):
        """
        TODO: Почему не в init?
        """
        log.info(colored(f"Historical data from {self.exchange.dt_from}", "white"))

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
        self.exchange.close_all()
        self.account_stats.snapshot()
        self.account_stats.portfolio_info()
        self.account_stats.account_info()

        self.stop_tg_bot()

    def stop(self):
        self.exchange.close_all()
        self.trading_data.stop_listen()

    def final_info(self):
        """
        Завершение торговли (штатное или из-за ошибки).
        Сохранить все наработанные данные.
        """
        csv_dir = f"{self.base_dir}/front"
        df = pd.DataFrame()
        for strategy in self.strategies:
            rd = strategy.resampled_data(self.resample_rule, self.dt_start)
            df = df.append(rd)
        df.sort_index().to_csv(f"{csv_dir}/data.csv", float_format="%.2f")
        self.trade_stats.to_csv(f"{csv_dir}/trades.csv")
        self.account_stats.to_csv(f"{csv_dir}/stats.csv")
        if self.exchange.backtest:
            self.account_stats.print_summary()  # RESULTS

    def on_event(self, event, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        if dt >= self.dt_start and not self.exchange.backtest:
            log.info(f"EVENT {event} {symbol} {payload}")

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
            if not self.exchange.backtest:
                self.account_stats.portfolio_info()
                self.account_stats.account_info()

        return True

    def on_bar(self, dt: datetime, symbol, payload):
        """
        Новый интервал. Обновить данные в стратегиях.
        Получить сигналы, зависящие от интервалов.
        """
        hints = []

        for strategy in self.strategies:
            if strategy.symbol == symbol:
                hints.append(strategy.on_bar(payload))

        self.process_hints(hints, dt)

    def on_trade(self, dt: datetime, symbol, payload):
        """
        Новая цена. Обновить данные в стратегиях.
        Получить сигналы, зависящие от сделок.
        """
        hints = []

        for strategy in self.strategies:
            if strategy.symbol == symbol:
                hints.append(strategy.on_trade(payload.price))

        self.process_hints(hints, dt)

    def process_hints(self, hints, dt):
        """
        Обновить состояние портфолио после получения новых сигналов.
        Применить новое состояние портфолио к торговому аккаунту.
        """
        hints = list(filter(None, hints))

        # Обновить Portfolio Targets
        self.portfolio.rebalance(hints)

        # Выставить ордеры
        self.execution.apply_targets(dt)
