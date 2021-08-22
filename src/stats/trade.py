import pandas as pd


class TradeStats:
    def __init__(self):
        self.trades = []

    def on_trade(self, dt, symbol, payload):
        self.trades.append(
            {
                "date": dt,
                "symbol": symbol,
                "side": payload["side"],
                "amount": payload["amount"],
                "price": float(payload["price"]),
                "profit": float(payload["profit"]) if payload["profit"] else None,
            }
        )

    def to_csv(self, file_name):
        if self.trades:
            df = pd.DataFrame(self.trades)
            df = df.set_index("date")
            df.to_csv(file_name, float_format="%.2f")
        else:
            open(file_name, "w").close()
