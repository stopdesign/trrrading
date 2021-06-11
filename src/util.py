import json
from datetime import datetime
from decimal import Decimal
from collections import defaultdict
from termcolor import colored, cprint


def interval_dt(interval):
    return datetime.fromtimestamp(interval["timestamp"] // 1000)


def trades_to_ohlc(item) -> dict:
    """
    Конвертер формата: list of trades >> OHLC
    """
    timestamp, trades = item
    prices = [Decimal(t["price"]) for t in trades]
    res = {
        "timestamp": timestamp,
        "open": prices[0],
        "low": min(prices),
        "close": prices[-1],
        "high": max(prices),
    }
    return res


def reformat_ohlc(data, interval_size):
    """
    Сгруппировать OHLC в более крупные интервалы.
    """

    trades_by_interval = defaultdict(list)

    for interval in data:
        ts = interval["timestamp"]
        ts_q = (1 + ts // (1000 * interval_size)) * interval_size
        trades = [
            {"price": interval["open"]},
            {"price": interval["high"]},
            {"price": interval["low"]},
            {"price": interval["close"]},
        ]
        trades_by_interval[ts_q * 1000] += trades

    return list(map(trades_to_ohlc, trades_by_interval.items()))


def normalize_ohlc(data, interval_size=60):
    """
    Добавить отсутствующие интервалы
    """

    data = sorted(data, key=lambda x: x["timestamp"])

    res = []
    prev_interval = None

    for interval in data:
        if not prev_interval:
            res.append(interval)
            prev_interval = interval
            continue

        t1 = prev_interval["timestamp"] // 1000
        t2 = interval["timestamp"] // 1000

        if t2 - t1 > interval_size:
            # fill the gap with fake intervals
            for t in range(t1 + interval_size, t2, interval_size):
                new_interval = dict(prev_interval)
                new_interval["timestamp"] = t * 1000
                new_interval["fake"] = True
                res.append(new_interval)

        res.append(interval)

        prev_interval = interval

    return res


def mark_extra_intervals(data):
    for interval in data:
        dt = datetime.fromtimestamp(interval["timestamp"] / 1000)
        extra = "     "
        # TODO: учесть часовой пояс и летнее время
        if dt.hour >= 22 or (dt.hour < 15 or (dt.hour == 15 and dt.minute < 30)):
            extra = "EXTRA"
        # TODO: учесть нестандартные выходные
        if dt.weekday() >= 5:
            extra = "EXTRA"
        if extra.strip():
            interval["extra"] = True
        # print(dt, interval.get("fake", "    "), extra)
    return data


def print_trade_final_info(
    dt,
    position,
    position_open_dt,
    profit,
    profit_rel,
    cash,
    cash_initial,
    max_potential_cash,
    max_drawdown,
    local_max_potential_cash,
    local_max_drawdown,
):
    total_profit = (cash - cash_initial) / cash_initial * 100
    pos_sign = colored("↗", "green") if position == "LONG" else colored("↘", "red")
    trade = f" {profit:+8.2f}  {profit_rel:+6.2f}% "
    total = f" Σ {cash:5.0f} {total_profit:+4.0f}% "
    color = "white"

    length = dt - position_open_dt
    if length.days > 0:
        length_str = colored(f"{length.days:>3}d", attrs=["bold"])
    elif length.seconds // 3600 > 0:
        length_str = colored(f"{(length.seconds // 3600):>3}h", "white")
    else:
        length_str = colored(f"{(length.seconds // 60):>3}m", "red")

    if profit > 0:
        color = "green"
    if profit < 0:
        color = "red"
    txt = f"{position_open_dt:%Y-%m-%d %H:%M}  {pos_sign} {length_str}  "
    txt += colored(trade, color, attrs=["reverse"])
    color = "white"
    if total_profit > 0:
        color = "green"
    if total_profit < 0:
        color = "red"
    txt += "  " + colored(total, color, attrs=["reverse"])
    # txt += f"   max cash: {max_potential_cash:6.0f}"
    txt += colored(f"   ↓ {local_max_drawdown:2.0f}%", attrs=["bold"])  # ⟱
    txt += colored(f"  {max_drawdown:0.0f}%", "white")
    print(txt)


def print_summary(
        position,
        profit,
        profit_rel,
        cash,
        cash_initial,
        max_drawdown,
        local_max_drawdown,
):
    total_profit = (cash - cash_initial) / cash_initial * 100
    pos_sign = colored("↗", "green") if position == "LONG" else colored("↘", "red")
    trade = f" {profit:+8.2f}  {profit_rel:+6.2f}% "
    total = f" Σ {cash:5.0f} {total_profit:+4.0f}% "
    color = "white"

    if profit > 0:
        color = "green"
    if profit < 0:
        color = "red"
    txt = colored(trade, color, attrs=["reverse"])
    color = "white"
    if total_profit > 0:
        color = "green"
    if total_profit < 0:
        color = "red"
    txt += "  " + colored(total, color, attrs=["reverse"])
    # txt += f"   max cash: {max_potential_cash:6.0f}"
    txt += colored(f"   ↓ {local_max_drawdown:2.0f}%", attrs=["bold"])  # ⟱
    txt += colored(f"  {max_drawdown:0.0f}%", "white")
    print(txt)


def print_order_info(dt, signal, price, position_size, cash):
    res = (
        f"{dt}   {signal:<5} {price:7.2f}    "
        f"cash: {cash:9.2f}    "
        f"asset: {position_size:4.0f}"
    )
    if signal == "LONG":
        color = "green"
    elif signal == "SHORT":
        color = "red"
    else:
        color = "blue"
    cprint(res, color)


def load_from_file(file, dt_from=datetime(1900, 1, 1), symbol=None):
    data = []
    with open(file, "r") as f:
        min_ts = str(int(dt_from.timestamp()))
        for line in f.readlines():
            if line[14:27] < min_ts:
                continue
            interval = json.loads(line)
            if symbol:
                interval["symbolId"] = symbol
            data.append(interval)
    return data


def parse_quote(quote):
    return {
        "price": Decimal(quote["price"]),
        "size": Decimal(quote.get("size", 1)),
    }
