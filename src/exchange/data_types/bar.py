from dataclasses import dataclass


@dataclass
class Bar:
    date: None
    open: float
    high: float
    low: float
    close: float
    volume: int
    average: float
    barCount: int
    rth: bool
    ticker: str

    up: float
    dn: float

    def __getattr__(self, item):
        return None

    @classmethod
    def from_pandas(cls, nt):
        dct = {
            "date": nt.Index,
            "open": nt.open,
            "high": nt.high,
            "low": nt.low,
            "close": nt.close,
            "volume": nt.volume,
            "average": nt.average,
            "barCount": nt.barCount,
            "rth": nt.rth,
            "ticker": nt.ticker,
            "up": None,
            "dn": None,
        }
        return cls(**dct)

    @classmethod
    def from_fake_trade(cls, ticker, date, price, volume):
        dct = {
            "date": date,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume,
            "average": price,
            "barCount": 1,
            "rth": 1,
            "ticker": ticker,
            "up": None,
            "dn": None,
        }
        return cls(**dct)
