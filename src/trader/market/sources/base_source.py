from datetime import datetime


class BaseSource:
    def __init__(self) -> None:
        pass

    def __str__(self) -> str:
        return self.__class__.__name__

    def load(self, instruments: list, dt_1: datetime, dt_2: datetime):
        raise NotImplementedError()

    def listen(self, instruments: list, on_market_event):
        raise NotImplementedError()
