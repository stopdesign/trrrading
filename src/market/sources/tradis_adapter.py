import json
import logging
from datetime import datetime, timezone
from time import sleep

import orjson

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

    def __str__(self) -> str:
        host = self.redis.get_connection_kwargs().get("host")
        return f"{self.__class__.__name__}(host={host})"

    def format_message(self, message):

        # Игнорировать subscribe messages
        if message and message.get("type") == "subscribe":
            return

        # Сервис Market data не прислал данные вовремя
        if message is None:
            log.error("Market data timeout")
            return

        # Парсер JSON
        try:
            data = orjson.loads(message["data"])
        except Exception as e:
            log.error(f"Bad json: {message}, {e}")
            return

        # Легкий фикс формата
        try:
            symbol = data["symbol"]
            data["dt"] = parse_dt(data["dt"])
        except KeyError:
            log.error(f"Bad format: {data}")
            return

        # Биржа совсем закрыта
        if "closed" in data:
            # log.info(f"{symbol}, {data['dt']} closed market bar")
            return

        # Биржа открыта, но пришел пустой бар
        if "empty" in data:
            # log.info(f"{symbol}, {data['dt']} empty bar")
            return

        # Сервис Market data работает, но актуальных данных в нем нет
        if data.get("delay"):
            log.warning(f"{symbol}, {data['dt']} delay")
            return

        if not ("price" in data or "vol" in data):
            try:
                dump = json.dumps(data, default=str)
            except:
                dump = str(data)
            log.warning(f"Unknown format: {dump}")
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

                if self.schedule.is_rth(s, data["dt"]):
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
                log.error(f"Redis pubsub get_message error: {e}")
                sleep(1)
                continue

            try:
                if payload := self.format_message(message):
                    on_market_event(payload)
            except Exception as e:
                log.exception(e)
