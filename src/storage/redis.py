import json
import logging
import orjson
import redis
from time import sleep
from datetime import timedelta, datetime, timezone
from data_types import BidAsk, Trade, Bar
from storage.ib import load_many
from termcolor import cprint, colored
from django.conf import settings

log = logging.getLogger("redis_storage")


# @TODO отправить в utils/helpers
def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class RedisTradingData:

    def __init__(self, instruments, dt_start, dt_end, on_event, backtest, **kwargs):
        self.instruments = instruments
        self.dt_start = dt_start
        self.dt_end = dt_end
        self.dt_from = kwargs.get("dt_from", self.dt_start - timedelta(days=30))
        self.on_event = on_event
        self.backtest = backtest
        self.symbols = list(self.instruments.keys())
        self.dt_last = None
        self.no_quotes_mode = False

        self.redis = redis.Redis(
            host=settings.TREDIS_HOST,
            port=settings.TREDIS_PORT,
            db=settings.TREDIS_DB,
            password=settings.TREDIS_PASSWORD,
        )

    def warm_up(self):
        """
        Прогнать события по историческим данным.
        """

        from_ts = str(dt_to_ts(self.dt_from)).encode()
        start_ts = str(dt_to_ts(self.dt_start)).encode()

        # TODO: написать штуку, которая будет загружать данные из redis в удобном виде
        # TODO: поддержка нескольких инструментов

        # FIXME: временная мера
        one_symbol = self.symbols[0]

        #######################
        # @TODO zrangebyscore скоро перестанет работать, т.к. deprecated
        quotes = self.redis.zrangebyscore(f"{one_symbol}:QUOTES", from_ts, start_ts)
        if len(quotes):
            log.info(f"warm_up quotes: {len(quotes)}")
        else:
            log.warning(colored(f"warm_up quotes: {len(quotes)}", "red"))
            self.no_quotes_mode = True

        trades = self.redis.zrangebyscore(f"{one_symbol}:TRADES", from_ts, start_ts)
        log.info(f"warm_up trades: {len(trades)}")

        all_data = sorted(quotes + trades)

        for line in all_data:
            data = orjson.loads(line.decode('utf-8'))
            symbol = one_symbol

            if "." in data["dt"]:
                dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S.%f")
            else:
                dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S")

            self.interval_event(dt)

            # Это quote
            if data.get("av_bid"):
                payload = BidAsk(date=dt, bid=data["av_bid"], ask=data["av_ask"])
                self.on_event("quote", dt, symbol, payload)

            # Это bar
            if data.get("o"):

                if self.no_quotes_mode:
                    payload = BidAsk(date=dt, bid=data["l"], ask=data["h"])
                    self.on_event("quote", dt, symbol, payload)

                for price in {data["o"], data["h"], data["l"], data["c"]}:
                    payload = Trade(date=dt, price=price, volume=data["vol"])
                    self.on_event("trade", dt, symbol, payload)

                payload = Bar(
                    date=dt,
                    open=data["o"],
                    high=data["h"],
                    low=data["l"],
                    close=data["c"],
                    volume=data["vol"],
                    average=0,
                    barCount=1,
                    rth=True,
                    ticker=symbol,
                    up=0,
                    dn=0,
                )
                self.on_event("bar", dt, symbol, payload)

    def start_listen(self):
        if self.backtest:
            return self.start_listen_emulation()
        else:
            return self.start_listen_real()

    def start_listen_emulation(self):
        """
        Эмулировать события, приходящие с биржи.
        """
        start_ts = str(dt_to_ts(self.dt_start)).encode()

        if self.dt_end:
            end_ts = str(dt_to_ts(self.dt_end)).encode()
        else:
            end_ts = 10 ** 10

        # FIXME: временная мера
        one_symbol = self.symbols[0]

        #######################
        data_in_db = self.redis.zrangebyscore(f"{one_symbol}:QUOTES", start_ts, end_ts)
        data_in_db += self.redis.zrangebyscore(f"{one_symbol}:TRADES", start_ts, end_ts)

        log.info(f"backtest data lines: {len(data_in_db)}")
        print()

        all_data = sorted(data_in_db)

        for line in all_data:
            data = orjson.loads(line.decode('utf-8'))
            symbol = one_symbol

            if "." in data["dt"]:
                dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S.%f")
            else:
                dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S")

            self.interval_event(dt)

            # Это quote
            if data.get("av_bid"):
                payload = BidAsk(date=dt, bid=data["av_bid"], ask=data["av_ask"])
                self.on_event("quote", dt, symbol, payload)

            # Это bar
            if data.get("o"):

                # print(data)

                # Симуляция QUOTES
                if self.no_quotes_mode:
                    payload = BidAsk(date=dt, bid=data["l"], ask=data["h"])
                    self.on_event("quote", dt, symbol, payload)

                # Симуляция отдельных сделок из OHLC
                for price in {data["o"], data["h"], data["l"], data["c"]}:
                    payload = Trade(date=dt, price=price, volume=data["vol"])
                    self.on_event("trade", dt, symbol, payload)

                # Минутные TRADES в виде OHLC
                payload = Bar(
                    date=dt,
                    open=data["o"],
                    high=data["h"],
                    low=data["l"],
                    close=data["c"],
                    volume=data["vol"],
                    average=0,
                    barCount=1,
                    rth=True,
                    ticker=symbol,
                    up=0,
                    dn=0,
                )
                self.on_event("bar", dt, symbol, payload)

    def start_listen_real(self):
        """
        Эмулировать события, приходящие с биржи.
        """

        one_symbol = self.symbols[0]

        pubsub = self.redis.pubsub()

        pubsub.subscribe(f"{one_symbol}:TRADES")
        # pubsub.subscribe("AAPL.NASDAQ:TRADES")
        # pubsub.subscribe("MNTS.NASDAQ:TRADES")
        # pubsub.subscribe("URA.ARCA:TRADES")

        pubsub.subscribe(f"{one_symbol}:BARS")
        # pubsub.subscribe("AAPL.NASDAQ:BARS")
        # pubsub.subscribe("MNTS.NASDAQ:BARS")
        # pubsub.subscribe("URA.ARCA:BARS")

        while True:
            message = pubsub.get_message()
            if message and not message['data'] == 1:
                try:
                    data = json.loads(message['data'].decode('utf-8'))
                except Exception as e:
                    cprint(message, "red")
                    data = None

                if data:
                    if "price" in data:
                        # TRADE
                        # cprint(json.dumps(data, default=str), "cyan")
                        # FIXME: time data '2022-02-18 16:41:20' does not match format
                        if "." in data["dt"]:
                            dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S.%f")
                        else:
                            dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S")
                        payload = Trade(date=dt, price=float(data["price"]), volume=0)
                        self.on_event("trade", dt, data["symbol"], payload)

                    elif "vol" in data:
                        # BAR
                        # cprint(json.dumps(data, default=str), "magenta")
                        dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S")
                        payload = Bar(
                            date=dt,
                            open=data["o"],
                            high=data["h"],
                            low=data["l"],
                            close=data["c"],
                            volume=data["vol"],
                            average=0,
                            barCount=1,
                            rth=True,
                            ticker=data["symbol"],
                            up=0,
                            dn=0,
                        )
                        self.on_event("bar", dt, data["symbol"], payload)

                        # Читерское получение quotes без настоящих данных
                        payload = BidAsk(date=dt, bid=data["l"], ask=data["h"])
                        self.on_event("quote", dt, data["symbol"], payload)

                    else:
                        cprint(json.dumps(data, default=str), "yellow")

            sleep(0.001)

    def stop_listen(self):
        pass

    def load_data(self):
        df = load_many(self.symbols, ["TRADES", "BIDASK"], start=self.dt_from.date())
        # BIDASK должен приходить раньше TRADES для этого интервала
        return df.sort_values(["date", "ticker", "data_type"])

    def interval_event(self, dt):
        """
        Запустить интервальное событие при необходимости.
        """
        if self.dt_last and dt.minute != self.dt_last.minute:
            norm_dt = dt.replace(minute=0, second=0, microsecond=0)
            if dt.day != self.dt_last.day:
                norm_dt = norm_dt.replace(hour=0)
                self.on_event("day", norm_dt)
            elif dt.hour != self.dt_last.hour:
                self.on_event("hour", norm_dt)
            elif dt.minute != self.dt_last.minute:
                self.on_event("minute", norm_dt)
        self.dt_last = dt
