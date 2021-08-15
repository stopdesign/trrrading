import os
import orjson
from datetime import datetime
from decimal import Decimal
from collections import defaultdict
from termcolor import colored, cprint
import requests


def interval_dt(interval):
    return datetime.utcfromtimestamp(interval["timestamp"] // 1000)


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
    txt = f"{position_open_dt}  {pos_sign} {length_str}  "
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


def read_line_ts(f, byte):
    f.seek(byte)
    lines = f.readlines(1000)
    return int(lines[1][14:27]) // 1000


def load_from_file(file, dt_from=datetime(1900, 1, 1), symbol=None):
    """
    Загрузка данных из файла с бинарным поиском нужной даты.
    """

    min_ts = int(dt_from.timestamp())

    # найти дату плюс-минус 5 дней (на случай праздников)
    min_diff = 3600 * 24 * 5

    data = []

    with open(file) as f:
        step = os.path.getsize(file) // 2
        pos = step

        # binary search for the time before min_ts
        for _ in range(10):
            step = step // 2
            diff = read_line_ts(f, pos) - min_ts
            # print(_, datetime.utcfromtimestamp(read_line_ts(f, pos)), (diff // 3600))
            if diff >= 0:
                pos -= step
                continue
            elif diff < -min_diff:
                pos += step
                continue
            else:
                break
        else:
            ts = read_line_ts(f, 0)
            dt = datetime.utcfromtimestamp(ts)
            pos = 0
            cprint(f"Line for {dt_from} not found {file} {dt}", "red")

        f.seek(pos)
        f.readline()  # skip incomplete line

        for line in f:
            if line[14:27] < str(min_ts):
                continue
            interval = orjson.loads(line)
            if symbol:
                interval["symbolId"] = symbol
            data.append(interval)

    return data


def load_from_ib_file(dt_from=datetime(1900, 1, 1), symbol=None):
    f = "/Users/gregory/projects/life/trrrading/src/history/ARCA/COPX/trades.txt"
    import pandas as pd
    import numpy as np

    min_ts = int(dt_from.timestamp()) * 1000

    df = pd.read_csv(f, sep="\t", index_col="date", dtype=str)
    df["symbolId"] = symbol
    df.sort_index(inplace=True)
    df["timestamp"] = (
        pd.to_datetime(df.index, utc=True).values.astype(np.int64) // 10 ** 6
    )
    df = df[df["timestamp"] > min_ts]
    df = df[df["timestamp"] <= 1626206400000]
    return df.to_dict(orient="records")


def load_quotes_from_ib_file(dt_from=datetime(1900, 1, 1), symbol=None):
    f = "/Users/gregory/projects/life/trrrading/src/history/ARCA/COPX/bidask.txt"
    import pandas as pd
    import numpy as np

    min_ts = int(dt_from.timestamp()) * 1000

    df = pd.read_csv(f, sep="\t", index_col="date", dtype=str)
    df["symbolId"] = symbol
    df.sort_index(inplace=True)
    df["timestamp"] = (
        pd.to_datetime(df.index, utc=True).values.astype(np.int64) // 10 ** 6
    )
    df = df[df["timestamp"] > min_ts]
    df = df[df["timestamp"] <= 1626206400000]
    df = df[["timestamp", "av_bid", "av_ask", "symbolId"]]

    df_rows = df.to_dict(orient="records")

    for row in df_rows:
        row["ask"] = [{"price": row["av_ask"], "size": 100}]
        row["bid"] = [{"price": row["av_bid"], "size": 100}]

    return df_rows


def fix_splits(ticker, trades):
    ticker = ticker.split(".")[0]
    params = "interval=3mo&events=split&period1=1400000000&period2=1800000000"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{params}"
    res = requests.get(url, headers={"User-Agent": "Godzilla"})
    try:
        splits = res.json()["chart"]["result"][0]["events"]["splits"]
        splits = sorted(splits.values(), key=lambda x: x["date"], reverse=True)
    except:
        return trades

    # for split in splits:
    #     print(datetime.utcfromtimestamp(split["date"]), split)

    for trade in trades:
        rate = Decimal("1")
        for split in splits:
            if int(trade["timestamp"]) < int(split["date"] * 1000):
                # splits.pop(0)
                rate = rate * split["denominator"] / split["numerator"]

        if rate != 1:
            # print(trade)
            # print(trade["close"], rate)
            trade["open"] = str(Decimal(trade["open"]) * rate)
            trade["high"] = str(Decimal(trade["high"]) * rate)
            trade["low"] = str(Decimal(trade["low"]) * rate)
            trade["close"] = str(Decimal(trade["close"]) * rate)

    return trades


def parse_quote(quote):
    return {
        "price": Decimal(quote["price"]),
        "size": Decimal(quote.get("size", 1)),
    }


DT_ZERO = datetime(1970, 1, 1)


def unix_timestamp(dt, micro=False):
    ts = int((dt - DT_ZERO).total_seconds())
    if micro:
        ts *= 1000
    return ts


def log_trade(
    log,
    dt,
    symbol,
    trigger_price,
    market_price,
    current_position,
    advised_position,
    amount_diff,
    total_sell,
    total_buy,
):
    symbol_str = colored(f"{symbol:>10}", attrs=["bold"])
    color, sign = "cyan", "*** "
    if amount_diff > 0:
        color, sign = "green", "+"
    if amount_diff < 0:
        color, sign = "red", "-"
    action = colored(f"{(sign + str(abs(amount_diff))):>5}", color)
    price_diff = abs(trigger_price - market_price) / market_price * 100
    txt = (
        f"\n{dt:%Y-%m-%d %H:%M:%S}  {symbol_str}   "
        f"cur/adv: {current_position:+6.0f} {advised_position:+6.0f}   "
        f"sig: {total_buy:+5.0f} {-total_sell:+5.0f}   "
        f"do: {action}    𝝙: {price_diff:0.2f}%"
    )
    txt = txt.replace("+0", colored(" 0", "white"))
    log.info(txt)
    # send_telegram(txt)


def log_trade_result(log, exchange, payload):
    txt = ""  # f"Close {partial_close_amount} {symbol}  "
    color = "white"
    profit = payload["profit"]
    if not profit:
        return
    if profit > 0:
        color = "green"
    if profit < 0:
        color = "red"
    rel_profit = (profit / exchange.cash) * 100
    txt += colored(f"Σ {exchange.cash:0.0f}  ", "grey")
    txt += colored(f"{profit:+0.2f}  ", color)
    txt += colored(f"{rel_profit:+0.2f}%  ", color)
    log.info(txt)
