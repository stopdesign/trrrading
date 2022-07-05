from datetime import datetime


class BaseSource:
    def __init__(self) -> None:
        pass

    def load(self, symbols: list, dt_1: datetime, dt_2: datetime):
        raise NotImplementedError()

    def listen(self):
        raise NotImplementedError()
