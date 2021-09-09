import pytz
import pandas_market_calendars as mcal
from datetime import datetime, timedelta

start = datetime.utcnow() - timedelta(days=3000)
end = datetime.utcnow() + timedelta(days=1000)
cal = mcal.get_calendar("NYSE").schedule(start, end)

# EST = UTC-4 / UTC-5
est = pytz.timezone("America/New_York")

by_days = {}
for day, t in sorted(cal.T.to_dict("list").items()):
    # Regular trading hours
    t0 = t[0].to_pydatetime()
    t1 = t[1].to_pydatetime()
    # Extended trading hours
    e0 = t0 - timedelta(hours=5, minutes=30)
    e1 = t1 + timedelta(hours=4)
    by_days[day.date()] = [t0, t1, e0, e1]


def trading_session(dt):
    """
    None — в выходные;
    False — в рабочие дни за пределами сессии;
    ["main", "pre", "post"] — во время сессии.
    """
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=pytz.UTC)
    day = dt.astimezone(est).date()
    t0, t1, e0, e1 = by_days.get(day, (None, None, None, None))
    # Holiday
    if not (t0 and t1):
        return None
    # Early Trading Session
    if e0 <= dt < t0:
        return "pre"
    # Core Trading Session
    if t0 <= dt < t1:
        return "main"
    # Late Trading Session
    if t1 <= dt < e1:
        return "post"
    # Doesn't fit in any Trading Session
    return False


def time_to_next_session(dt, main=True):
    """
    Возвращает timedelta == 0, если сессия уже идет,
    или timedelta > 0 до начала следующей сессии.
    """
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=pytz.UTC)
    ts = trading_session(dt)
    if main and ts == "main":
        return timedelta()
    if not main and ts:
        return timedelta()
    for i in range(10):
        new_dt = dt + timedelta(days=i)
        day = new_dt.astimezone(est).date()
        if times := by_days.get(day):
            t0, t1, e0, e1 = times
            if main and t0 > dt:
                return t0 - dt
            elif e0 > dt:
                return e0 - dt
    raise ValueError("No trading session in many days")


if __name__ == "__main__":
    test_dt = "2021-08-13 23:59:59+00:00"
    test_dt = datetime.strptime(test_dt, "%Y-%m-%d %H:%M:%S%z")
    # test_dt = test_dt.astimezone(pytz.timezone("Europe/Amsterdam"))
    # test_dt = test_dt.replace(tzinfo=None)

    print(test_dt, test_dt.tzinfo)
    print(trading_session(test_dt))
    print("to main", time_to_next_session(test_dt))
    print("to extra", time_to_next_session(test_dt, main=False))
