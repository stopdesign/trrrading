import logging
import pandas as pd
from termcolor import colored

log = logging.getLogger("trade")


class TradeStats:
    def __init__(self):
        self.trades = []

    def on_trade_done(self, dt, symbol, payload):
        self.trades.append(
            {
                "date": dt,
                "symbol": symbol,
                "side": payload["side"],
                "amount": payload["amount"],
                "price": payload["price"],
                "slippage": payload["slippage"],
                "fee": payload["fee"],
                "profit": payload["profit"] if payload["profit"] else None,
                "net_value": payload["net_value"],
            }
        )

    def to_csv(self, file_name):
        df = pd.DataFrame.from_records(self.trades, index=["date"], coerce_float=True)
        df.to_csv(file_name, float_format="%.2f")

    def log_trade_result(self, _, payload):
        txt = "Trade result: "
        color = "white"
        profit = payload["profit"]
        if not profit:
            return
        if profit > 0:
            color = "green"
        if profit < 0:
            color = "red"
        txt += colored(f"{profit:+0.2f}  ", color)
        log.info(txt)

    @staticmethod
    def log_trade(
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
        symbol_str = colored(f"{symbol:<10}", attrs=["bold"])
        color, sign = "cyan", "*** "
        if amount_diff > 0:
            color, sign = "green", "+"
        if amount_diff < 0:
            color, sign = "red", "-"
        action = colored(f"{(sign + str(abs(amount_diff))):>5}", color)
        rel_slippage = abs(trigger_price - market_price) / market_price * 100
        txt = (
            f"{dt:%Y-%m-%d %H:%M:%S}  {symbol_str}   "
            f"cur/adv: {current_position:+6.0f} {advised_position:+6.0f}   "
            f"sig: {total_buy:+5.0f} {-total_sell:+5.0f}   "
            f"do: {action}    𝝙: {rel_slippage:0.2f}%    price: {market_price:0.2f}"
        )
        txt = txt.replace("+0", colored(" 0", "white"))
        log.info(txt)
        # send_telegram(txt)
