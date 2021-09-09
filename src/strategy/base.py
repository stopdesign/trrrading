import pandas as pd
from .signal import Signal


class BaseStrategy:

    interval_size = 60

    def __init__(self, **kwargs):
        self.length = kwargs.get("length")
        self.params = kwargs
        self.data = []
        self.historical = []
        self.on_start()

    def __repr__(self):
        params = ""
        for key, value in self.params.items():
            params += f" {key}={value}"
        return f"<{type(self).__name__}{params}>"

    def add_to_historical(self, data):
        self.historical += data

    def on_start(self):
        pass

    def on_bar(self, data):
        pass

    def on_quote(self, data):
        pass

    def on_trade(self, data):
        pass

    def test_price(self, price: float) -> Signal:
        return Signal.PASS

    def resampled_data(self, resample_rule, dt_start=None):
        df = pd.DataFrame(self.data)
        if not df.empty:
            df.set_index("date", inplace=True)
            if dt_start:
                df = df[df.index > dt_start]
            if resample_rule:
                df = df.resample(resample_rule).apply({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "average": "mean",
                    "barCount": "sum",
                    "rth": "first",
                    "ticker": "last",
                    "up": "max",
                    "dn": "min",
                })
            df.dropna(inplace=True)
        return df
