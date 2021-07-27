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
                "profit": 0,
            }
        )

    def to_csv(self, file_name):
        df = pd.DataFrame(self.trades)
        df = df.set_index("date")
        df.to_csv(file_name)
