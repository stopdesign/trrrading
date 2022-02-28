from dataclasses import dataclass
from datetime import datetime
from typing import Union
from ib_insync import BarData


@dataclass
class Bar:
    date: Union[None, datetime]
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

    @classmethod
    def from_bar_data(cls, bd: BarData, ticker):
        """
        date: Union[date_, datetime] = EPOCH
        open: float = 0.0
        high: float = 0.0
        low: float = 0.0
        close: float = 0.0
        volume: int = 0
        average: float = 0.0
        barCount: int = 0
        """
        dct = {
            "date": bd.date.replace(tzinfo=None),
            "open": bd.open,
            "high": bd.high,
            "low": bd.low,
            "close": bd.close,
            "volume": bd.volume,
            "average": bd.average,
            "barCount": bd.barCount,
            "rth": 1,
            "ticker": ticker,
            "up": None,
            "dn": None,
        }
        return cls(**dct)
