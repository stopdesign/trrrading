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
