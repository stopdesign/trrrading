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
            sid = data["sid"]
            data["dt"] = parse_dt(data["dt"])
        except KeyError:
            log.error(f"Bad format: {data}")
            return

        # Биржа совсем закрыта
        if "closed" in data:
            # log.info(f"{sid}, {data['dt']} closed market bar")
            return

        # Биржа открыта, но пришел пустой бар
        if "empty" in data:
            # log.info(f"{sid}, {data['dt']} empty bar")
            return

        # Сервис Market data работает, но актуальных данных в нем нет
        if data.get("delay"):
            log.warning(f"{sid}, {data['dt']} delay")
            return

        if not ("price" in data or "vol" in data or "o" in data):
            try:
                dump = json.dumps(data, default=str)
            except:
                dump = str(data)
            log.warning(f"Unknown format: {dump}")
            return

        return data

    def load(self, sids, dt_1, dt_2):
        t1 = dt_to_ts(dt_1)
        t2 = dt_to_ts(dt_2)

        all_data = []

        # Загрузить все данные, разметить
        for s in sids:
            lns = self.redis.zrangebyscore(f"{s}:TRADES", t1, t2, withscores=True)
            if self.quotes:
                lns += self.redis.zrangebyscore(f"{s}:QUOTES", t1, t2, withscores=True)

            # prev_str = None
            # prev = {"c": None}
            for data_str, score in sorted(lns):
                data = orjson.loads(data_str)
                # Легкий фикс формата
                data["sid"] = s
                data["dt"] = parse_dt(data["dt"])

                # # Если данные поменялись, но vol == 0 — поставить 1
                # if '"o"' in data_str:
                #     no = data["o"] == data["h"] == data["l"] == data["c"] == prev["c"]
                #     if prev_str != data_str[28:] and '"vol":0' in data_str and not no:
                #         data["vol"] = -1
                #     prev_str = data_str[28:]
                #     prev = data

                if self.schedule.is_rth(s, data["dt"]):
                    all_data.append((score, s, data))

        log.info(f"{sids}, {dt_1}, {dt_2}, {len(all_data)}")

        # Отсортировать по score и символу
        return sorted(all_data)

    def listen(self, sids, on_market_event, on_broker_event):
        """
        Подписка на события в Redis pubsub.
        """
        pubsub = self.redis.pubsub()

        # Подписка на pubsub
        for sid in sids:
            pubsub.subscribe([f"{sid}:TRADES", f"{sid}:BARS"])

        # FIXME: плохо всё это держать в одной подписке, т.к. ломается timeout
        # Ну или нужно руками считать timeout по типам сообщений.
        # В любом случае SYNC лучше отсюда вынести. Это не часть канала данных.
        pubsub.subscribe(["SYNC"])  # подписка на события от брокера

        while True:
            try:
                message = pubsub.get_message(timeout=100)
            except Exception as e:
                log.error(f"Redis pubsub get_message error: {e}")
                sleep(1)
                continue

            try:
                if message and message.get("channel") == "SYNC":
                    if message.get("type") == "message":
                        on_broker_event(message.get("data"))
                elif payload := self.format_message(message):
                    on_market_event(payload)
            except Exception as e:
                log.exception(e)
