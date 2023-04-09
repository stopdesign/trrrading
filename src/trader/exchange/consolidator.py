from trader.data_types import Bar

from .data import Data


class Consolidator(Data):
    """
    Собирает бар более крупного таймфрейма.
    Вызывает событие on_bar, когда бар готов.

    NOTE: Возможно, имеет тот же интерфейс, что и Data.

    Бар открывается при появлении первых данных, которые в него
    должны попасть. Данные продолжают накапливаться в данном
    баре, пока не придет что-нибудь из следующего бара.

    class Bar:
        date: datetime
        sid: str
        open: Decimal
        high: Decimal
        low: Decimal
        close: Decimal
        volume: int = None
        rth: bool = None
    """
    def __init__(self, data: Data, rule: str, on_bar=None) -> None:
        self.data = data
        self.rule = rule
        self.sid = data.sid
        self.on_bar = on_bar
        self.bars: list[Bar] = []
        self.inner_bars: list[Bar] = []
        self.version : int = 0
        self.step = 60 * int(rule.replace("m", ""))
        self.closed_bar = None

    def __repr__(self) -> str:
        return f"Consolidator({self.data}, rule={self.rule})"

    def _close(self):
        if not self.inner_bars:
            return
        bar_0 = self.inner_bars[0]
        bar_1 = self.inner_bars[-1]
        res = {
            "date": bar_0.date,
            "sid": bar_0.sid,
            "open": bar_0.open,
            "high": None,
            "low": None,
            "close": bar_1.close,
            "volume": None,
            "rth": bar_0.rth,
        }
        res["high"] = max([b.high for b in self.inner_bars])
        res["low"] = min([b.low for b in self.inner_bars])
        res["volume"] = sum([b.volume for b in self.inner_bars])
        self.bars.append(Bar(**res))
        self.inner_bars = []

    def add_bar(self, bar: Bar) -> None:
        ts = int(bar.date.timestamp())
        if int(ts // self.step) > self.version:
            self.version = int(ts // self.step)
            self._close()
            self.inner_bars = [bar]
        else:
            self.inner_bars.append(bar)

    def trigger_events(self) -> None:
        if self.on_bar and self.bars:
            self.on_bar(self.bars[-1])
