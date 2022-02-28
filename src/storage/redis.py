import json
from time import sleep

import orjson
import redis
from datetime import timedelta, datetime, timezone
from data_types import BidAsk, Trade, Bar
from storage.ib import load_many
from termcolor import cprint


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class RedisTradingData:

    def __init__(self, instruments, dt_start, dt_end, on_event, **kwargs):
        self.instruments = instruments
        self.dt_start = dt_start
        self.dt_end = dt_end
        self.on_event = on_event
        self.dt_from = kwargs.get("dt_from", self.dt_start - timedelta(days=30))
        self.symbols = self.instruments.keys()
        self.dt_last = None

        self.redis = redis.Redis(db=6)

    def warm_up(self):
        """
        Прогнать события по историческим данным.
        """

        from_ts = str(dt_to_ts(self.dt_from)).encode()
        start_ts = str(dt_to_ts(self.dt_start)).encode()

        # TODO: написать штуку, которая будет загружать данные из redis в удобном виде
        # TODO:

        #######################
        data_in_db = self.redis.zrangebyscore("MES.GLOBEX:QUOTES", from_ts, start_ts)
        data_in_db += self.redis.zrangebyscore("MES.GLOBEX:TRADES", from_ts, start_ts)

        print(">>>>>", len(data_in_db))

        all_data = sorted(data_in_db)

        for line in all_data:
            data = orjson.loads(line.decode('utf-8'))
            symbol = "MES.GLOBEX"

            if "." in data["dt"]:
                dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S.%f")
            else:
                dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S")

            self.interval_event(dt)

            # Это bar
            if data.get("avg"):

                for price in {data["o"], data["h"], data["l"], data["c"]}:
                    payload = Trade(price=price, volume=data["vol"])
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

            # Это quote
            if data.get("av_bid"):
                payload = BidAsk(bid=data["av_bid"], ask=data["av_ask"])
                self.on_event("quote", dt, symbol, payload)

    def start_listen(self):
        """
        Эмулировать события, приходящие с биржи.
        """
        start_ts = str(dt_to_ts(self.dt_start)).encode()
        end_ts = str(dt_to_ts(self.dt_end)).encode()

        #######################
        data_in_db = self.redis.zrangebyscore("MES.GLOBEX:QUOTES", start_ts, end_ts)
        data_in_db += self.redis.zrangebyscore("MES.GLOBEX:TRADES", start_ts, end_ts)

        print(">>>>>", len(data_in_db))

        all_data = sorted(data_in_db)

        for line in all_data:
            data = orjson.loads(line.decode('utf-8'))
            symbol = "MES.GLOBEX"

            if "." in data["dt"]:
                dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S.%f")
            else:
                dt = datetime.strptime(data["dt"], "%Y-%m-%d %H:%M:%S")

            self.interval_event(dt)

            # Это bar
            if data.get("avg"):
                for price in {data["o"], data["h"], data["l"], data["c"]}:
                    payload = Trade(price=price, volume=data["vol"])
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

            # Это quote
            if data.get("av_bid"):
                payload = BidAsk(bid=data["av_bid"], ask=data["av_ask"])
                self.on_event("quote", dt, symbol, payload)


        return

        pubsub = self.redis.pubsub()

        pubsub.subscribe("MES.GLOBEX:TRADES")
        # pubsub.subscribe("AAPL.NASDAQ:TRADES")
        # pubsub.subscribe("MNTS.NASDAQ:TRADES")
        # pubsub.subscribe("URA.ARCA:TRADES")

        pubsub.subscribe("MES.GLOBEX:BARS")
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
                        payload = Trade(price=float(data["price"]), volume=0)
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
                        payload = BidAsk(bid=data["l"], ask=data["h"])
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
