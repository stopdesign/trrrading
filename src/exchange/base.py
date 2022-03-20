from datetime import datetime
from decimal import Decimal
from typing import Optional
from data_types import Margin, Fee


class BaseExchange:
    """
    Биржа
    """

    # FIXME: заменить price на None
    empty_position = {"amount": Decimal("0"), "price": Decimal("0")}

    backtest = False
    margin = Margin()
    fee = Fee()

    def __init__(self, symbols, **kwargs):
        self.symbols = symbols
        self.on_event = kwargs.get("on_event")
        self.quotes = {}
        self.positions = {}
        self.cash = Decimal(0)
        self.cash_initial = self.cash
        self.last_event = {}
        self.finished = False
        self.dt_start = kwargs.get("dt_start")  # дата начала теста/торговли
        self.dt_end = kwargs.get("dt_end")  # дата завершения теста
        self.dt_from = None   # начало интервала для предзаполнения истории
        self.dt_last = None   # фактический последний/текущий интервал

    def get_price(self, symbol: str, side: str) -> Optional[float]:
        if quotes := self.quotes.get(symbol):
            if side == "sell":
                return quotes["bid"]
            if side == "buy":
                return quotes["ask"]
            if side == "mid":
                return (quotes["ask"] + quotes["bid"]) / 2

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
            self.quotes[symbol]["ask"] = payload.ask
            self.quotes[symbol]["dt"] = dt
        if payload.bid:
            self.quotes[symbol]["bid"] = payload.bid
            self.quotes[symbol]["dt"] = dt
        self.dt_last = dt

    def trade(self, side: str, amount: float, symbol: str, dt: datetime, sig_price):
        raise NotImplementedError()

    def print_final_info(self):
        pass

    def get_positions(self):
        return self.positions

    def get_cash_value(self):
        pass

    @property
    def net_value(self):
        raise NotImplementedError()

    @property
    def equity_value(self):
        return

    def get_margin_level(self, short=False):
        return self.margin.short if short else self.margin.long
