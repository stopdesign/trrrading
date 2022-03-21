from decimal import Decimal


class Exchange:
    """
    Биржа. Хранит Quotes.
    Умеет считать цену инструмента для разных направлений сделки.
    """

    def __init__(self):
        self.quotes = {}
        self.dt_last = None

    def get_price(self, symbol: str, side: str) -> Decimal:
        if quotes := self.quotes.get(symbol):
            if side == "sell":
                return quotes["bid"]
            if side == "buy":
                return quotes["ask"]
            if side == "mid":
                return (quotes["ask"] + quotes["bid"]) / 2
        return Decimal("nan")

    def add_quote(self, dt, symbol, payload):
        """
        Сохранить BID и ASK как актуальное состояние стакана на бирже.
        """
        current_quote = self.quotes.get(symbol)
        if current_quote and current_quote["dt"] > dt:
            return
        if symbol not in self.quotes:
            self.quotes[symbol] = {}
        # ask и bid могут приходить независимо
        if payload.ask:
            self.quotes[symbol]["ask"] = Decimal(payload.ask)
            self.quotes[symbol]["dt"] = dt
        if payload.bid:
            self.quotes[symbol]["bid"] = Decimal(payload.bid)
            self.quotes[symbol]["dt"] = dt
        self.dt_last = dt
