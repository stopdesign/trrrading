from trader.data_types import Bar


class Data:
    """
    Хранит рыночные данные, вызывает события в стратегии.
    Интерфейс для доступа к данным из стратегии.
    """

    def __init__(self, sid: str, rth: int = 0, on_bar=None, on_tick=None) -> None:
        self.sid = sid
        self.rth = rth
        self.on_bar = on_bar
        self.on_tick = on_tick
        self.bars: list[Bar] = []
        self.version : int = 0

    def add_bar(self, bar: Bar) -> None:
        self.version = int(bar.date.timestamp())
        self.bars.append(bar)

    def trigger_events(self) -> None:
        if self.on_bar and self.bars:
            self.on_bar(self.bars[-1])
