import logging
from copy import copy
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
from termcolor import colored
from data_types import Hint, Bar, Trade
from stats import PortfolioStats, StrategyStats
from storage.redis import RedisTradingData
from trader import Exchange, Portfolio, TelegramBotMixin, Execution
from strategy import all_strategies, Signal
from main.models import Account, Run

log = logging.getLogger("trader")


def date_to_datetime(dt):
    return datetime(dt.year, dt.month, dt.day)


class Trader(TelegramBotMixin):
    exchange: Exchange = None
    strategies: list = None

    def __init__(self, broker_conf, strategy_conf, backtest):
        dt_now = datetime.utcnow().replace(microsecond=0)
        txt = f"Init Trader(backtest={backtest}) at {dt_now}"
        log.info(colored(txt, "white"))

        self.backtest = backtest
        self.symbols = sorted(list({c["symbol"] for c in strategy_conf}))
        self.target_margin = Decimal(broker_conf.get("target_margin"))

        # if self.backtest:
        #     account = None
        # else:
        #     account = Account.objects.get(
        #         uid=broker_conf["account"],
        #         username=broker_conf["username"],
        #     )
        #     # Отдельный запуск торговли
        #     self.run = Run.objects.create(
        #         account=account,
        #         backtest=self.backtest,
        #         broker_config=json.dumps(broker_conf, indent=2, default=str),
        #         strategy_config=json.dumps(strategy_conf, indent=2, default=str),
        #     )

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
        self.trading_data = RedisTradingData(
            symbols=self.symbols,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
            backtest=self.backtest,
        )

        # Прогреть индикторы прогоном исторических данных.
        # На этом этапе еще нет портфолио, только сигналы и Hint.
        self.trading_data.warm_up()

        # Список стратегий, результаты прогрева
        for strategy in self.strategies:
            log.info(colored(f"{strategy.info}", "grey"))

        self.portfolio = Portfolio(self.exchange, self.strategies, self.target_margin)

        # Сделать разным для backtest и торговли?
        # self.execution = Execution(self.exchange, self.portfolio, self.run)

        self.portfolio_stats = PortfolioStats(self, self.portfolio, self.target_margin)

        self.strategy_stats = StrategyStats(self.strategies, self.portfolio)

        # Для реальной торговли подгружается фактическое состояние
        # self.update_portfolio()

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

    # def update_portfolio(self):
    #     """
    #     Для бэктеста все инструменты из конфига устанавливаются в 0.
    #     Для торговли берется состояние из базы данных для данного аккаунта.
    #     Отсутствующие инструменты из конфига устанавливаются в 0.
    #     """
    #     if not self.backtest:
    #         self.exchange.latest_order_id = Order.objects.latest('id').id
    #
    #         # Для торговли через брокера позиции выставляются по значениям из базы
    #         for position in Position.objects.filter(account=self.run.account):
    #             instrument = position.instrument
    #             symbol = instrument.symbol + "." + instrument.main_exchange.symbol
    #             self.exchange.positions[symbol] = {
    #                 "amount": position.amount,
    #                 "price": position.avg_price,
    #                 "dt": position.updated_at,
    #             }

    def start(self):
        self.start_tg_bot()

        log.info(colored(" Start stream ", "green", attrs=["reverse"]))

        self.portfolio_stats.snapshot()

        try:
            # Для бэктеста это заканчивается,
            # для торговли крутится до прерывания
            self.trading_data.start_listen()
        except KeyboardInterrupt:
            log.info(colored(" Stop stream ", "red", attrs=["reverse"]))
        except Exception as e:
            log.exception(e)

        if self.backtest:
            self.close_all()
            self.strategy_stats.save_all()
            self.portfolio_stats.print_summary()  # RESULTS

        self.stop_tg_bot()

    def on_event(self, event, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        if dt > self.dt_start and not self.backtest:
            log.info(f"EVENT {event} {symbol} {payload}")

        if event == "bar":
            self.on_bar(dt, symbol, payload)

        if event == "trade":
            self.on_trade(dt, symbol, payload)

        if event == "quote":
            self.exchange.add_quote(dt, symbol, payload)

        if event in ["hour", "day", "after_trade"]:
            if dt > self.dt_start:
                self.portfolio_stats.snapshot()

        if event == "after_trade":
            log.info("EVENT after_trade")
            # self.trade_stats.on_trade_done(dt, symbol, payload)
            # self.account_stats.on_trade_done(symbol, payload)
            # self.trade_stats.log_trade_result(symbol, payload)
            #
            # # if not self.backtest:
            # self.account_stats.portfolio_info()
            # self.account_stats.account_info()

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
                if strategy.data and dt > self.dt_start:
                    self.strategy_stats.append(strategy, dt)

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
        # self.execution.apply_targets(dt)
