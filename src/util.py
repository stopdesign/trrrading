from datetime import datetime
from decimal import Decimal
from termcolor import colored, cprint


def interval_dt(interval):
    return datetime.utcfromtimestamp(interval["timestamp"] // 1000)


def parse_quote(quote):
    return {
        "price": Decimal(quote["price"]),
        "size": Decimal(quote.get("size", 1)),
    }


DT_ZERO = datetime(1970, 1, 1)


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
    rel_slippage = abs(trigger_price - market_price) / market_price * 100
    txt = (
        f"\n{dt:%Y-%m-%d %H:%M:%S}  {symbol_str}   "
        f"cur/adv: {current_position:+6.0f} {advised_position:+6.0f}   "
        f"sig: {total_buy:+5.0f} {-total_sell:+5.0f}   "
        f"do: {action}    𝝙: {rel_slippage:0.2f}%"
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
