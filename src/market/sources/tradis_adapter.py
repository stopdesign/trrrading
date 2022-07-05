import logging
from datetime import datetime, timezone
from time import sleep

import orjson
from termcolor import colored

from .base_source import BaseSource

log = logging.getLogger("tradis_adapter")


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def parse_dt(dt: str) -> datetime:
    if "." not in dt:
        dt += ".000000"
    return datetime.strptime(dt, "%Y-%m-%d %H:%M:%S.%f")


class TradisAdapter(BaseSource):
    def __init__(self, redis_client):

        # Есть ли в базе QUOTES
        self.quotes = False

        self.redis = redis_client

    def format_message(self, message):

        # Игнорировать subscribe messages
        if message and message.get("type") == "subscribe":
            return

        # Случился таймаут
        if message is None:
            log.error(colored("Redis pubsub timeout", "red"))
            return

        # Парсер JSON
        try:
            data = orjson.loads(message["data"])
        except Exception as e:
            log.error(colored(f"Bad json: {message}, {e}", "red"))
            return

        # Легкий фикс формата
        try:
            symbol = data["symbol"]
            data["dt"] = parse_dt(data["dt"])
        except KeyError:
            log.error(colored(f"Bad format: {data}", "red"))
            return

        # Биржа совсем закрыта
        if "closed" in data:
            # log.info(f"{symbol}, {data['dt']} closed market bar")
            return

        # Биржа открыта, но пришел пустой бар
        if "empty" in data:
            log.info(f"{symbol}, {data['dt']} empty bar")
            return

        if not ("price" in data or "vol" in data):
            log.error(colored(f"Unknown format: {data}", "red"))
            return

        return data

    def load(self, symbols, dt_1, dt_2):
        t1 = dt_to_ts(dt_1)
        t2 = dt_to_ts(dt_2)

        all_data = []

        # Загрузить все данные, разметить
        for s in symbols:
            lns = self.redis.zrangebyscore(f"{s}:TRADES", t1, t2, withscores=True)
            if self.quotes:
                lns += self.redis.zrangebyscore(f"{s}:QUOTES", t1, t2, withscores=True)

            for data, score in lns:
                data = orjson.loads(data)
                # Легкий фикс формата
                data["symbol"] = s
                data["dt"] = parse_dt(data["dt"])
                all_data.append((score, s, data))

        log.info(f"{symbols}, {dt_1}, {dt_2}, {len(all_data)}")

        # Отсортировать по score и символу
        return sorted(all_data)

    def listen(self, symbols, on_market_event):
        """
        Подписка на события в Redis pubsub.
        """
        pubsub = self.redis.pubsub()

        # Подписка на pubsub
        for symbol in symbols:
            pubsub.subscribe(f"{symbol}:TRADES")
            pubsub.subscribe(f"{symbol}:BARS")

        while True:
            try:
                message = pubsub.get_message(timeout=100)
            except Exception as e:
                log.error(colored(e, "red"))
                sleep(1)
                continue

            try:
                if payload := self.format_message(message):
                    on_market_event(payload)
            except Exception as e:
                log.exception(e)
