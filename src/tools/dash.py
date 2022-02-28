from collections import Counter
import logging

import orjson
import redis
from datetime import datetime, timedelta, timezone


log = logging.getLogger("dash")

r = redis.Redis(host='localhost', port=6379, db=6)


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def get_stats_for_hour(data):
    cnt = Counter()

    for line in data:
        try:
            j = orjson.loads(line.decode())
        except ValueError:
            cnt["error"] += 1
            continue
        if j.get("error"):
            cnt["error"] += 1
        elif j.get("closed"):
            cnt["closed"] += 1
        elif j.get("empty"):
            cnt["empty"] += 1
        elif j.get("fix") or j.get("late"):
            cnt["fix"] += 1
        else:
            cnt["ok"] += 1

    return cnt


def main():
    dt = datetime.now()

    csv_path = "/Users/gregory/projects/life/trrrading/front/dash/dash.csv"

    # Посчитать tumestamp начала графика
    start = datetime.utcnow() - timedelta(hours=80)
    start = start.replace(minute=0, second=0, microsecond=0)

    dash_csv_data = "ticker,group,ok,closed,error,fix,empty\n"

    for key in r.keys():
        key = key.decode()

        cur_hour_interval = start
        for n in range(300):
            # Запросить данные для этого интервала
            data = r.zrangebyscore(
                key,
                dt_to_ts(cur_hour_interval),
                dt_to_ts(cur_hour_interval) + 3599
            )
            stats = get_stats_for_hour(data)
            dash_csv_data += (
                f"{key},{cur_hour_interval},"
                f"{stats['ok']},{stats['closed']},"
                f"{stats['error']},{stats['fix']},"
                f"{stats['empty']}\n"
            )

            cur_hour_interval += timedelta(hours=1)
            if cur_hour_interval > datetime.utcnow():
                break

    with open(csv_path, "w") as f:
        f.write(dash_csv_data)

    print(f"Done in {str(datetime.now() - dt)[:-7]}")


if __name__ == "__main__":
    main()
