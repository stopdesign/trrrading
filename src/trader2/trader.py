import json
import logging
from copy import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import redis
from data_types import Bar
from market import DataProvider, PolygonAdapter, TradisAdapter
from strategy import all_strategies
from termcolor import colored

# from trader import Exchange, Executor, BTExecutor, Portfolio

log = logging.getLogger("trader")


REDIS_CONF = {
    "decode_responses": True,
    "socket_keepalive": True,
    "socket_timeout": 300,
    "health_check_interval": 3,
}


def date_to_datetime(dt):
    return datetime(dt.year, dt.month, dt.day)



class Emulator:
    """
    Эмулятор торговли.

    Получает торговые данные из событий трейдера.
    Обновляет данные Portfolio ***из самого себя*** при новых сигналах.
    Когда бот создает ордер, добавляет его в Portfolio.
    Обрабатывает выставленные ордеры.
    При срабатывании ордера запускает событие, которое пробросится в стратегии.
    """
    def __init__(self, on_event):
        self.positions = {}
        self.orders = []
        self.account = {}
        self.quotes = {}
        self.time = None

        self.on_event = on_event
    
    def process_order(self, order):
        """
        Посмотреть список ордеров и изобразить их исполнение по известным ценам.
        """
        print("process_order")

        order.status = "filled"

        quotes = self.quotes["URA.ARCA"]
        order.fill_price = (quotes.bid + quotes.ask) / 2

        position = self.positions.get("URA.ARCA", 0)
        self.positions["URA.ARCA"] = position + order.amount

        log.info(f"FILL ORDER {self.time} {order}")

        # сначала закончить исполнение всех ордеров, потом дергать события?
        self.on_event("order_emulator", dt=self.time, payload=order)
    
    def on_quote(self, dt, bid_ask):
        self.time = dt
        self.quotes["URA.ARCA"] = bid_ask

    def on_bar(self, dt, bar):
        """
        Если пришли новые данные, проверить ордеры в portfolio.orders,
        исполнить что-нибудь, запустить событие order_event.
        """
        self.time = dt

        for order in self.orders:
            if order.status == "new":
                self.process_order(order)

    def place_order(self, order):
        """
        market-order можно обработать сразу,
        другие типы будут обработаны при поступлении новых данных.
        Хотя, limit тоже может сработать сразу, если цена позволяет...
        """
        self.orders.append(order)
        self.process_order(order)

    def on_portfolio(self, payload):
        """
        Кажется, в режиме эмуляции это событие не должно возникать.
        """
        # raise NotImplementedError
        pass

    def on_order(self, order):
        # обновился ордер, записать его в orders
        pass



class Exchange:
    """
    Живая торговля.

    Получает торговые данные из событий трейдера.
    Получает события от синхронизатора. // portfolio update, order event
    Обновляет данные Portfolio ***из базы*** при новых сигналах.
    Когда бот создает ордер, добавляет его в orders и дергает синхронизатор.
    """
    def __init__(self, on_event):
        self.positions = {}
        self.orders = []
        self.account = {}
        self.quotes = {} 

        self.on_event = on_event

        # TODO загрузить данные в self.positions, self.account...
    
    def process_order(self, order):
        raise Exception("Live order shouldn't be processed here")

    def on_bar(self, dt, bar):
        # TODO обновить self.quotes
        pass

    def place_order(self, order):
        self.orders.append(order)
        # в живой торговле нужно сообщить об этом в sync - КАК ЭТО СДЕЛАТЬ?

    def on_portfolio(self, payload):
        # TODO обновить данные в self.positions, self.account...
        pass

    def on_order(self, order):
        # ордер обновился на стороне биржи, записать это в orders
        pass



class Trader2:
    """
    Есть три режима: live, backtest, replay.
    Реальная торговля идет от now до остановки скрипта.
    Бэктест идет от dt_start до dt_end.
    Replay идет от dt_start до dt_end, но через feed.

    Replay - это как бэктест, только данные поступают событиями через redis.
    """
    data_provider: DataProvider = None
    strategies: list = None

    def __init__(self, config, backtest, replay):
        dt_now = datetime.utcnow().replace(microsecond=0)
        txt = f"Init Trader(backtest={backtest}) at {dt_now}"
        log.info(colored(txt, "white"))

        self.config = config
        self.backtest = backtest
        self.replay = replay

        run_config = config["backtest"] if backtest else config["live"]

        self.symbols = sorted(list({c["symbol"] for c in config["strategies"]}))
        self.config_start_end(run_config, warm_up=timedelta(days=2))
        self.config_sources(run_config, config["sources"])

        # Добывает данные, запускает события
        self.data_provider = DataProvider(
            symbols=self.symbols,
            history=self.history_source,  # исторические данные одной кучей
            feed=self.feed_source,        # real-time потоковые данные
            dt_prior=self.dt_prior,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
        )

        if self.backtest or self.replay:
            # Для backtest - передать в эмулятор объекты OPA
            self.exchange = Emulator(self.on_event)
            # TODO начальное состояние аккаунта при эмуляции
        else:
            # Для live торговли подписаться на обновление OPA
            self.exchange = Exchange(self.on_event)

        # Инициализация стратегий
        # Собрать все индикаторы
        self.strategies = []
        self.indicators = []
        for cfg in config["strategies"]:
            strategy_class = all_strategies[cfg["strategy"]]
            strategy = strategy_class(exchange=self.exchange, **cfg)
            self.strategies.append(strategy)
            self.indicators += list(strategy.indicators)

        # Прогреть индикторы прогоном исторических данных.
        self.data_provider.warm_up()

        # Отметить, что стратегии прогреты.
        # Может, лучше сделать это внутри стратегии?
        for strategy in self.strategies:
            strategy.warmed = True


    def on_event(self, event, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.

        Порядок событий пока хрен знает какой.
        """
        if dt > self.dt_start:  # and not self.backtest:
            # log.info(f"EVENT {event} {symbol} {payload}")
            pass

        if event == "quote":
            self.exchange.on_quote(dt, payload)

        if event == "bar":
            # пройтись по всем индикаторам и обновить их
            for indicator in self.indicators:
                indicator.on_bar(copy(payload))

            # TODO сложить данные индикаторов и баров в удобном виде в стратегии

            for strategy in self.strategies:
                strategy.on_bar(copy(payload))

        if event == "trade":
            for strategy in self.strategies:
                strategy.on_trade(copy(payload))

        # Эмулятор сообщает об изменениях ордера
        if event == "order_emulator":
            # проброс в стратегии
            # TODO пробрасывать только в стратегию, которая ордер создала
            for strategy in self.strategies:
                strategy.on_order_event(copy(payload))
        
        # LIVE: Брокер сообщает об изменении ордера, позиций или аккаунта
        if event == "broker":

            # обновить ордер в полях биржи
            self.exchange.on_order(copy(payload))

            # обновить поля биржи
            self.exchange.on_portfolio(copy(payload))

            # вызвать событие в стратегиях
            for strategy in self.strategies:
                strategy.on_order_event(copy(payload))

        if event in ["day"]:
            if dt > self.dt_start:
                print(f"\n{dt}\n")
        
        # Обработка новых торговых данных эмулятором
        if self.backtest and dt > self.dt_start and event == "bar":
            # Дернуть эмулятор биржи.
            # Пробросить в него очередную порцию данных,
            # запросить обработку открытых ордеров.
            self.exchange.on_bar(dt, copy(payload))


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
            log.info(redis_client)
            self.feed_source = TradisAdapter(redis_client)
        elif "polygon" in feed:
            self.feed_source = PolygonAdapter(**feed_conf)
        else:
            raise ValueError(f"Unknown feed source: {feed}")
        
        log.info(self.feed_source)

    def start(self):

        print()
        log.info(colored(" Start ", "green", attrs=["reverse", "bold"]))

        if self.backtest:
            self.data_provider.backtest()
        else:
            try:
                self.data_provider.listen()
            except KeyboardInterrupt:
                pass
            except Exception as e:
                log.exception(e)

        log.info(colored(" Stop ", "red", attrs=["reverse", "bold"]))

