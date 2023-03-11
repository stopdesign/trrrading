"""
Скрипт берет из Redis исторические данные и начинает их выдавать в pubsub,
как будто это живые данные.

Можно регулировать скорость (кратно) и количество сделок в минуту.
На первой скорости BARS поступают раз в минуту, как и положено.

Отдельные TRADES считаются из минутных BARS.

Redis db keys:
*.TRADES — бары в базе данных

Redis stream channels:
*.TRADES — сделки в стримe
*.BARS — минутные бары в стриме
"""

import sys
import click
import json
import orjson
import yaml
import redis
from time import sleep
from os.path import abspath
from random import randint
from datetime import datetime, timezone, timedelta


dt_format = click.DateTime(formats=["%Y-%m-%d %H:%M:%S"])


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def get_key(instrument, mode=None):
    res = f"{instrument['symbol']}.{instrument['exchange']}"
    if mode:
        res += f":{mode}"
    return res


class Emulator:

    def __init__(self, redis_client, instruments, speed, start, end, suffix, debug):
        self.redis_client = redis_client
        self.instruments = instruments
        self.speed = speed
        self.start = start
        self.end = end
        self.suffix = suffix
        self.debug = debug
        self.upcoming = []
        self.bars = {}

        print("redis_client", redis_client)

        if not self.end:
            self.end = self.start + timedelta(hours=20)

        self.preload_data()

    def preload_data(self):

        start_ts = dt_to_ts(self.start)
        end_ts = dt_to_ts(self.end)

        print("Preload bars:")

        for instrument in self.instruments:
            self.bars[instrument["symbol"]] = {}

            key = get_key(instrument, "TRADES")
            data = self.redis_client.zrangebyscore(key, start_ts, end_ts)

            print(f"{key:<20} {len(data):>10}")

            for line in data:
                bar = orjson.loads(line.decode())
                self.bars[instrument["symbol"]][bar["dt"]] = bar

    def start_stream(self):
        """
        Вызывает self.tick на каждую секунду эмулируемого времени,
        начиная со start. Скорость перебора секунд определяется speed.
        """
        t0 = datetime.utcnow().replace(microsecond=0) + timedelta(seconds=1)
        next_target_delta = 0
        while True:
            delta = (datetime.utcnow() - t0).total_seconds() * self.speed
            if delta > next_target_delta:
                emulated_time = self.start + timedelta(seconds=delta)

                # Время для нового бара
                if emulated_time.second == 0:
                    for instrument in self.instruments:
                        self.events_for_instrument(emulated_time, instrument)

                # Отправить события, запланированные на эту секунду
                self.tick(emulated_time)

                next_target_delta += 1
            sleep(0.0001)

    def events_for_instrument(self, emulated_time, instrument):
        """
        Достать новый бар для данной минуты,
        сгенерить N событий для сделок со смещением по времени,
        сгенерить событие для отправки бара.
        """
        dt_str = emulated_time.strftime("%Y-%m-%d %H:%M:%S")
        bar = self.bars[instrument["symbol"]].get(dt_str)
        if not bar:
            sys.tracebacklimit = 0
            raise Exception(f"END OF DATA: {dt_str}, {instrument}")

        # key = get_key(instrument, "TRADES")

        # # TODO: поддержка произвольного количества, разброс цены

        # if "o" in bar:
        #     dt = emulated_time + timedelta(seconds=randint(3, 10))
        #     self.upcoming.append(dict(dt=dt, key=key, trade=bar["o"]))

        # if "h" in bar:
        #     dt = emulated_time + timedelta(seconds=randint(10, 40))
        #     self.upcoming.append(dict(dt=dt, key=key, trade=bar["h"]))

        # if "l" in bar:
        #     dt = emulated_time + timedelta(seconds=randint(10, 40))
        #     self.upcoming.append(dict(dt=dt, key=key, trade=bar["l"]))

        # if "c" in bar:
        #     dt = emulated_time + timedelta(seconds=randint(40, 58))
        #     self.upcoming.append(dict(dt=dt, key=key, trade=bar["c"]))

        # Положить бар в список со смещением после закрытия бара
        key = get_key(instrument, "BARS")
        dt = emulated_time + timedelta(seconds=randint(65, 75))
        self.upcoming.append(dict(dt=dt, key=key, bar=bar))

    def tick(self, emulated_time):
        """
        Перебрать upcoming, отправить созревшие, удалить их из списка.
        """
        events_left = []
        for event in self.upcoming:
            if event["dt"] <= emulated_time:
                self.publish_event(event)
            else:
                events_left.append(event)

        self.upcoming = events_left

        # Проверить, что количество не увеличивается бесконтрольно
        assert len(self.upcoming) < 500

    def publish_event(self, event):
        """
        Форматирует и отправляет событие в pubsub Redis.
        """
        payload = None

        if "bar" in event:
            bar = dict(event["bar"])
            bar["symbol"] = event["key"].split(":")[0]
            if "late" in bar:
                del bar["late"]
            payload = json.dumps(bar, indent=None, default=str)

        if "trade" in event:
            msg = {
                "dt": event["dt"].strftime("%Y-%m-%d %H:%M:%S"),
                "price": event["trade"],
                "conid": 0,
                "symbol": event["key"].split(":")[0],
            }
            payload = json.dumps(msg, indent=None, default=str)

        if payload:
            key = event["key"] + self.suffix
            if self.debug:
                print("publish_event:", key, payload)
            self.redis_client.publish(key, payload)


@click.command()
@click.argument("config", nargs=1, default="../config/tradis.yaml")
@click.option("--start", type=dt_format, default="2022-03-02 20:00:00")
@click.option("--end", type=dt_format, default=None)
@click.option("--speed", type=int, default=1)
@click.option("--suffix", type=str, default="")
@click.option("--debug", is_flag=True, default=False)
def main(**kwargs):
    dt_start = kwargs.get("start")
    dt_end = kwargs.get("end")
    speed = kwargs.get("speed")
    suffix = kwargs.get("suffix")
    config_filename = kwargs.get("config")
    debug = kwargs.get("debug")

    # Загрузка конфига
    config_path = abspath(config_filename)
    config = yaml.full_load(open(config_path))

    redis_config = config["redis"]
    instruments = config["instruments"]

    redis_client = redis.Redis(
        host=redis_config["host"],
        port=redis_config["port"],
        db=redis_config["db"],
        password=redis_config["password"],
    )

    print(f"Historical data start point:\n{dt_start}\n")

    emulator = Emulator(redis_client, instruments, speed, dt_start, dt_end, suffix, debug)

    try:
        emulator.start_stream()
    except KeyboardInterrupt:
        print("DONE")


if __name__ == "__main__":
    main()
