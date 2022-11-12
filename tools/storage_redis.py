from collections import Counter
import logging
import redis
from datetime import datetime, timedelta, timezone


log = logging.getLogger("dash")

r = redis.Redis(host='localhost', port=6379, db=6)


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def main():
    dt = datetime.now()

    # Посчитать tumestamp начала графика
    start = datetime.utcnow() - timedelta(hours=80)
    start = start.replace(minute=0, second=0, microsecond=0)
    start_ts = dt_to_ts(start)
    end_ts = 10**10

    key = "MES.GLOBEX:TRADES"

    # Запросить данные для этого интервала
    data = r.zrangebyscore(key, start_ts, end_ts)

    for line in data:
        line = line.decode()
        print(line.split(" "))

    print(f"Done in {str(datetime.now() - dt)[:-7]}")


if __name__ == "__main__":
    main()
