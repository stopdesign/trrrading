import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from termcolor import colored
from data_types import Hint, Bar, Trade
from exchange import BaseExchange, IBWebExchange
from stats import AccountStats, TradeStats
from storage.redis import RedisTradingData
from trader import Portfolio, TelegramBotMixin, Execution
from strategy import all_strategies
from main.models import Account, Run, Position, Order

log = logging.getLogger("trader")


def date_to_datetime(dt):
    return datetime(dt.year, dt.month, dt.day)


class Trader(TelegramBotMixin):
    exchange: BaseExchange = None
    strategies: list = None

    def __init__(self, broker_conf, instruments, backtest):
        dt_now = datetime.utcnow().replace(microsecond=0)
        txt = f"Init Trader(backtest={backtest}) at {dt_now}"
        log.info(colored(txt, "white"))

        self.backtest = backtest
        self.instruments = instruments

        if self.backtest:
            account = None
        else:
            account = Account.objects.get(
                uid=broker_conf["account"],
                username=broker_conf["username"],
            )

        # Отдельный запуск торговли или бэктеста
        self.run = Run.objects.create(
            account=account,
            backtest=self.backtest,
            broker_config=json.dumps(broker_conf, indent=2, default=str),
            strategy_config=json.dumps(instruments, indent=2, default=str),
        )

        self.target_margin = broker_conf.get("target_margin")

        self.init_strategies()

        # У бэктеста есть начало и конец, а реальная
        # торговля идет от now до остановки скрипта
        if self.backtest:
            self.dt_start = date_to_datetime(broker_conf.get("dt_start"))
            self.dt_end = date_to_datetime(broker_conf.get("dt_end")) + timedelta(1)
        else:
            self.dt_start = datetime.utcnow().replace(microsecond=0)
            self.dt_end = None

        self.exchange = IBWebExchange(
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

        self.portfolio = Portfolio(self.exchange)  # Все instruments по нулям

        self.execution = Execution(self.exchange, self.portfolio, self.run)

        self.account_stats = AccountStats(self, self.exchange)

        self.trade_stats = TradeStats(self, self.exchange)

        # Прогреть индикторы прогоном исторических данных.
        # На этом этапе еще нет портфолио, только сигналы и Hint.
        self.trading_data.warm_up()

        for strategy in self.strategies:
            log.info(colored(f"{strategy}, {strategy.prev_signal}", "grey"))

        # Для реальной торговли подгружается фактическое состояние
        self.update_portfolio()

        self.account_stats.portfolio_info()
        self.account_stats.account_info()

    def init_strategies(self):
        """
        Инициализация классов стратегий.
        """
        self.strategies = []
        for symbol, config in self.instruments.items():
            for strategy_conf in config["strategies"]:
                strategy_class = all_strategies[strategy_conf["name"]]
                self.strategies.append(strategy_class(symbol, **strategy_conf))

    def update_portfolio(self):
        """
        Для бэктеста все инструменты из конфига устанавливаются в 0.
        Для торговли берется состояние из базы данных для данного аккаунта.
        Отсутствующие инструменты из конфига устанавливаются в 0.
        """
        # Есть два портфолио: желаемое и реальное

        # Пустые значения для всех инструментов из конфига
        for symbol in self.instruments.keys():
            self.exchange.positions[symbol] = {
                "amount": Decimal(0),
                "price": Decimal(0),
            }

        if not self.backtest:
            self.exchange.latest_order_id = Order.objects.latest('id').id

            # Для торговли через брокера позиции выставляются по значениям из базы
            for position in Position.objects.filter(account=self.run.account):
                instrument = position.instrument
                symbol = instrument.symbol + "." + instrument.main_exchange.symbol
                self.exchange.positions[symbol] = {
                    "amount": position.amount,
                    "price": position.avg_price,
                    "dt": position.updated_at,
                }

    def start(self):
        self.start_tg_bot()

        log.info(colored(" Start stream ", "green", attrs=["reverse"]))

        self.account_stats.snapshot()

        try:
            # Для бэктеста это заканчивается,
            # для торговли крутится до прерывания
            self.trading_data.start_listen()
        except KeyboardInterrupt:
            log.info(colored(" Stop stream ", "red", attrs=["reverse"]))
            # self.trading_data.stop_listen()
        except Exception as e:
            log.exception(e)

        if self.backtest:
            self.close_all()
            self.account_stats.print_summary()  # RESULTS

        self.account_stats.snapshot()

        self.stop_tg_bot()

    def on_event(self, event, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        # if dt >= self.dt_start and not self.backtest:
        #     log.info(f"EVENT {event} {symbol} {payload}")

        if event == "bar":
            self.on_bar(dt, symbol, payload)

        if event == "trade":
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

        if dt > self.dt_start:
            self.process_hints(hints, dt)

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

        if dt > self.dt_start:
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
