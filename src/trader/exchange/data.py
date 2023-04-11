from trader.data_types import Bar


class Data:
    """
    Хранит рыночные данные, вызывает события в стратегии.
    Интерфейс для доступа к данным из стратегии.
    """

    def __init__(
        self,
        sid: str,
        *,
        rth: bool = False,
        on_bar=None,
        on_tick=None,
    ) -> None:
        self.sid = sid
        self.rth = rth
        self.on_bar = on_bar
        self.on_tick = on_tick
        self.bars: list[Bar] = []
        self.version: int = 0

    def __repr__(self) -> str:
        return f"Data({self.sid}, rth={self.rth})"

    def add_bar(self, bar: Bar) -> None:
        # Отрезаются ETH, если их не просили
        if (not self.rth) or bar.rth:
            self.version = int(bar.date.timestamp())
            self.bars.append(bar)

    def trigger_events(self) -> None:
        # bars
        if self.on_bar and self.bars:
            bar = self.bars[-1]
            self.on_bar(bar)

        # FIXME: здесь я ожидаю уже побитые бары или реальные сделки
        # # ticks ???
        # if self.on_tick and self.bars:
