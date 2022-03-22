import logging
import orjson
import redis
from functools import cache
from decimal import Decimal
from datetime import timedelta, datetime, timezone
from data_types import BidAsk, Trade, Bar
from termcolor import colored
from django.conf import settings
import pandas_market_calendars as mcal

log = logging.getLogger("redis_source")


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def parse_dt(dt: str) -> datetime:
    if "." not in dt:
        dt += ".000000"
    return datetime.strptime(dt, "%Y-%m-%d %H:%M:%S.%f")


EXCHANGE_SCHEDULE = {
    "NASDAQ": "NASDAQ",
    "NYMEX": "NYSE",
    "NYSE": "NYSE",
    "ARCA": "NYSE",
    "GLOBEX": "CME_Rate",
}


@cache
def get_calendar_and_schedule(exchange):
    """
    Календарь и расписание для биржи.
    """
    calendar = mcal.get_calendar(EXCHANGE_SCHEDULE[exchange])

    # нужно покрыть вперед и назад все возможные выходные
    start = datetime.utcnow() - timedelta(days=100)
    end = datetime.utcnow() + timedelta(days=100)

    # TODO: убрать хардкодинг
    if EXCHANGE_SCHEDULE[exchange] in ["NYSE", "NASDAQ"]:
        schedule = calendar.schedule(start, end)
    else:
        schedule = calendar.schedule(start, end)

    return calendar, schedule


@cache
def check_open_time(exchange, cur_interval):
    """
    Открыта ли эта биржа в указанный момент.
    """
    calendar, schedule = get_calendar_and_schedule(exchange)
    cur_interval_utc = cur_interval.replace(tzinfo=timezone.utc)
    try:
        return calendar.open_at_time(schedule, cur_interval_utc)
    except ValueError as e:
        print(schedule)
        raise e


class RedisTradingData:

    def __init__(self, symbols, dt_start, dt_end, on_event, backtest, **kwargs):
        self.symbols = symbols
        self.dt_start = dt_start
        self.dt_end = dt_end
        self.dt_from = kwargs.get("dt_from", self.dt_start - timedelta(days=10))
        self.on_event = on_event
        self.backtest = backtest
        self.dt_last = None

        # Есть ли в базе QUOTES
        self.quotes = False

        self.redis = redis.Redis(
            host=settings.TREDIS_HOST,
            port=settings.TREDIS_PORT,
            db=settings.TREDIS_DB,
            password=settings.TREDIS_PASSWORD,
        )

    def load_redis_data(self, symbols, t1, t2):
        all_data = []

        # Загрузить все данные, разметить
        for s in symbols:
            lns = self.redis.zrangebyscore(f"{s}:TRADES", t1, t2, withscores=True)
            if self.quotes:
                lns += self.redis.zrangebyscore(f"{s}:QUOTES", t1, t2, withscores=True)

            for data, score in lns:
                data = orjson.loads(data.decode())
                # Легкий фикс формата
                data["symbol"] = s
                data["dt"] = parse_dt(data["dt"])
                all_data.append((score, s, data))

        # Отсортировать по score и символу
        return sorted(all_data)

    def run_events(self, data: dict):

        self.interval_event(data["dt"])

        # Это quote
        if self.quotes and data.get("av_bid"):
            quote = BidAsk.from_redis_quote(data)
            self.on_event("quote", quote.date, quote.symbol, quote)

        # Это bar
        elif data.get("o"):

            if not self.quotes:
                quote = BidAsk.from_redis_trade(data)
                self.on_event("quote", quote.date, quote.symbol, quote)

            bar = Bar.from_redis(data)

            exchange_symbol = bar.symbol.split(".")[1]
            bar.rth = check_open_time(exchange_symbol, bar.date)

            for trade in self.bar_to_trades(bar):
                self.on_event("trade", trade.date, trade.symbol, trade)

            self.on_event("bar", bar.date, bar.symbol, bar)

    def bar_to_trades(self, bar: Bar) -> list[Trade]:
        """
        Разбивает минутный бар на отдельные сделки со смещением по 15 секунд.
        """
        trades = []
        dt = 5
        for price in {bar.open, bar.high, bar.low, bar.close}:
            trade = Trade(
                date=bar.date + timedelta(seconds=dt),
                symbol=bar.symbol,
                price=price,
                rth=bar.rth,
            )
            trades.append(trade)
            dt += 15
        return trades

    def warm_up(self):
        """
        Прогнать события по историческим данным.
        """

        from_ts = str(dt_to_ts(self.dt_from)).encode()
        start_ts = str(dt_to_ts(self.dt_start - timedelta(minutes=1))).encode()

        log.info(colored(f"Historical data for symbols {self.symbols}", "white"))
        log.info(colored(f"Warm up data from: {self.dt_from}", "white"))
        log.info(colored(f"Trading data from: {self.dt_start}", "white"))

        all_data = self.load_redis_data(self.symbols, from_ts, start_ts)

        log.info(f"warm_up data lines: {len(all_data)}")

        for score, symbol, data in all_data:
            self.run_events(data)

    def start_listen(self):
        if self.backtest:
            return self.start_listen_emulation()
        else:
            return self.start_listen_real()

    def start_listen_emulation(self):
        """
        Эмулировать события, приходящие с биржи.
        """
        start_ts = str(dt_to_ts(self.dt_start - timedelta(minutes=1))).encode()
        end_ts = str(dt_to_ts(self.dt_end)).encode() if self.dt_end else 10 ** 10

        all_data = self.load_redis_data(self.symbols, start_ts, end_ts)

        log.info(f"backtest data lines: {len(all_data)}")

        for score, symbol, data in all_data:
            self.run_events(data)

    def start_listen_real(self):
        """
        Подписка на события в Redis pubsub.
        """
        pubsub = self.redis.pubsub()

        trades_since_last_bar = {}

        for symbol in self.symbols:
            pubsub.subscribe(f"{symbol}:TRADES")
            pubsub.subscribe(f"{symbol}:BARS")
            trades_since_last_bar[symbol] = 1  # Изначально считаю, что сделки шли

        while True:
            message = pubsub.get_message(timeout=100)

            # Игнорировать subscribe messages
            if message and message.get("type") == "subscribe":
                continue

            # Случился таймаут
            if message is None:
                log.error(colored("Redis pubsub timeout", "red"))
                continue

            # Парсер JSON
            try:
                data = orjson.loads(message['data'].decode())
            except Exception as e:
                log.error(colored(f"Bad json: {message}, {e}", "red"))
                continue

            # Форматирование данных
            try:
                symbol = data["symbol"]
                data["dt"] = parse_dt(data["dt"])
            except KeyError:
                log.error(colored(f"Bad format: {data}", "red"))
                continue

            # Биржа совсем закрыта
            if "closed" in data:
                log.info(f"{symbol} market is closed")
                continue

            exchange_symbol = symbol.split(".")[1]
            is_rth = check_open_time(exchange_symbol, data["dt"])

            if "price" in data:
                # TRADE
                trades_since_last_bar[symbol] += 1
                trade = Trade(
                    date=data["dt"],
                    symbol=symbol,
                    price=Decimal(data["price"]),
                    rth=is_rth,
                )
                self.on_event("trade", trade.date, trade.symbol, trade)

            elif "vol" in data:
                # BAR

                # Читерское получение quotes без настоящих данных
                quote = BidAsk.from_redis_trade(data)
                self.on_event("quote", quote.date, quote.symbol, quote)

                bar = Bar.from_redis(data)
                bar.rth = is_rth

                # Если пришел новый бар, биржа работает, объем не нулевой,
                # но сделок с прошлого бара не приходило, то эмулировать сделки
                if trades_since_last_bar[symbol] < 1 and bar.volume > 0:
                    log.warning(colored(f"No trades for bar {bar}", "yellow"))
                    for trade in self.bar_to_trades(bar):
                        self.on_event("trade", trade.date, trade.symbol, trade)

                self.on_event("bar", bar.date, bar.symbol, bar)

                # Сбрасываю счетчик сделок
                trades_since_last_bar[symbol] = 0

            else:
                log.error(colored(f"Unknown format: {data}", "red"))

    def interval_event(self, dt):
        """
        Запустить интервальное событие при необходимости.
        """
        if self.dt_last and dt.minute != self.dt_last.minute:
            norm_dt = dt.replace(second=0, microsecond=0)
            if dt.day != self.dt_last.day:
                norm_dt = norm_dt.replace(hour=0, minute=0)
                self.on_event("day", norm_dt)
            elif dt.hour != self.dt_last.hour:
                norm_dt = norm_dt.replace(minute=0)
                self.on_event("hour", norm_dt)
            elif dt.minute != self.dt_last.minute:
                self.on_event("minute", norm_dt)
        self.dt_last = dt
