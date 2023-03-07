import json
import logging
from collections import defaultdict
from copy import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import redis
from termcolor import colored

from data_types import Bar, Order, BidAsk
from data_types.position import Position
from market import DataProvider, PolygonAdapter, TradisAdapter
from strategy import all_strategies

log = logging.getLogger("trader")


REDIS_CONF = {
    "decode_responses": True,
    "socket_keepalive": True,
    "socket_timeout": 300,
    "health_check_interval": 3,
}


def date_to_datetime(dt):
    return datetime(dt.year, dt.month, dt.day)


class LocalMatcher:
    """
    Исполняет ордер локально, используя исторические цены.

    Что здесь нужно?
    
    Position
        В реальной торговле position будет содержать дополнительную информацию:
            amount
            avg_price
            unrealized_pnl
        Для бэктеста в позиции может быть полезно держать статистику,
        но нужно ли делать это здесь?
    
    Order
        Ордер и его свойства.

    Account
        Параметры депозита


    Что будет происходить

    При поступлении новых торговых данных нужно попробовать исполнить ордеры,
    которые лежат в статусе new. Метод process_order принимает ордер и пытается
    его исполнить. Класс знает текущие позиции и цены. Класс делает всё,
    что происходило бы при реальном исполнении: меняет позиции, статус ордера, депозит.

    Цену исполнения ордера считает exchange, наверное, т.к. там этот метод нужен
    для других задач. Matcher занимается только изменением значений.

    """

    def __init__(self, exchange):
        self.exchange = exchange

    def process_order(self, order: Order):
        """
        Тип ордера: market, limit, stop.
        """
        process_order = False

        side = "buy" if order.amount > 0 else "sell"

        if order.type == "market":
            process_order = True
            price = self.exchange.get_price("URA.ARCA", side)  # "mid"
        
        if order.type == "limit":
            pass
        
        if order.type == "stop":
            # TODO: сделать нормальный алгоритм
            price = self.exchange.get_price("URA.ARCA", "mid")
            if order.amount > 0 and price > order.stop_price:
                process_order = True
                price = Decimal(order.stop_price)
            if order.amount < 0 and price < order.stop_price:
                process_order = True
                price = Decimal(order.stop_price)

        if process_order:

            order.status = "filled"
            order.fill_price = price

            # log.info(f"FILL ORDER {self.exchange.dt_last} {order}")

            # обновить позицию
            position = self.exchange.positions.get("URA.ARCA")

            new_amount = position.amount + order.amount
            trade_profit = position.update(new_amount, price)

            # обновить баланс
            self.exchange.account["net_value"] += trade_profit

            log.info(
                f"trade_profit: {trade_profit:0.2f} "
                f"net_value: {self.exchange.account['net_value']:0.2f} "
            )

            # сообщить стратегии о срабатывании ордера
            self.exchange.on_event("order_emulator", dt=self.exchange.dt_last, payload=order)


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
        self.quotes = {}  # последнее значение bid-ask
        self.bars = defaultdict(list)  # market data bar including indicators values
        self.dt_last = None
        self.on_event = on_event
        self.matcher = LocalMatcher(self)

    # NOTE: код из старого класса Exchange
    def get_price(self, symbol: str, side: str) -> Decimal:
        if quotes := self.quotes.get(symbol):
            if side == "sell":
                return quotes["bid"]
            if side == "buy":
                return quotes["ask"]
            if side == "mid":
                return (quotes["ask"] + quotes["bid"]) / 2
        return Decimal("nan")

    # NOTE: код из старого класса Exchange
    def add_quote(self, dt, symbol, payload):
        """
        Сохранить BID и ASK как актуальное состояние стакана на бирже.
        """
        current_quote = self.quotes.get(symbol)
        if current_quote and current_quote["dt"] > dt:
            return
        if symbol not in self.quotes:
            self.quotes[symbol] = {}
        # ask и bid могут приходить независимо
        if payload.ask:
            self.quotes[symbol]["ask"] = Decimal(payload.ask)
            self.quotes[symbol]["dt"] = dt
        if payload.bid:
            self.quotes[symbol]["bid"] = Decimal(payload.bid)
            self.quotes[symbol]["dt"] = dt
        self.dt_last = dt

    def process_orders(self):
        """
        Посмотреть список ордеров и изобразить их исполнение по известным ценам.
        """
        for order in self.orders:
            if order.status == "new":
                self.matcher.process_order(order)

    def on_quote(self, dt, bid_ask):
        self.add_quote(dt, "URA.ARCA", bid_ask)

    def on_bar(self, dt, bar):
        self.dt_last = dt
        self.bars["URA.ARCA"].append(copy(bar))

    def place_order(self, order):
        """
        Метод для создания ордера из стратегии.

        При эмуляции ордер может быть обработан сразу, если параметры позволяют.
        Необработанные ордеры будут проверяться при добавлении новых торговых данных.
        """
        self.orders.append(order)
        self.matcher.process_order(order)

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
            feed=self.feed_source,  # real-time потоковые данные
            dt_prior=self.dt_prior,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
        )

        if self.backtest or self.replay:
            # Для backtest - передать в эмулятор объекты OPA
            self.exchange = Emulator(self.on_event)
            
            # начальное состояние аккаунта при эмуляции
            self.exchange.account["net_value"] = 100_000
            # обнулить позиции по всем символам
            for symbol in self.symbols:
                self.exchange.positions[symbol] = Position(symbol, 100_000, Decimal(0))

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
            # 1. Добавить bar в хранилище баров
            self.exchange.on_bar(dt, payload)

            # 2. Обновить индикаторы, собрать их новые значения
            for indicator in self.indicators:
                indicator.on_bar(copy(payload))

            # 3. Передать bar в стратегии
            for strategy in self.strategies:
                strategy.on_bar(copy(payload))

            # 4. Запустить обработку ордеров
            self.exchange.process_orders()

        if event == "trade":
            # 3. Передать trade в стратегии
            for strategy in self.strategies:
                strategy.on_trade(copy(payload))

            # 4. Запустить обработку ордеров
            self.exchange.process_orders()

        # Эмулятор сообщает об изменениях ордера
        if event == "order_emulator":
            # TODO: пробрасывать только в стратегию, которая ордер создала
            for strategy in self.strategies:
                strategy.on_order_event(payload)

        # # LIVE: Брокер сообщает об изменении ордера, позиций или аккаунта
        # if event == "broker":

        #     # обновить ордер в полях биржи
        #     self.exchange.on_order(copy(payload))

        #     # обновить поля биржи
        #     self.exchange.on_portfolio(copy(payload))

        #     # вызвать событие в стратегиях
        #     for strategy in self.strategies:
        #         strategy.on_order_event(copy(payload))

        # if event in ["day"]:
        #     if dt > self.dt_start:
        #         print(f"\n{dt}\n")

        # # Обработка новых торговых данных эмулятором
        # if self.backtest and dt > self.dt_start and event == "bar":
        #     # Дернуть эмулятор биржи.
        #     # Пробросить в него очередную порцию данных,
        #     # запросить обработку открытых ордеров.
        #     self.exchange.on_bar(dt, copy(payload))

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
