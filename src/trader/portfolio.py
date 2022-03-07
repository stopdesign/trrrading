import logging
from decimal import Decimal
from math import floor
from exchange import BaseExchange
from strategy import Signal

log = logging.getLogger("portfolio")


class Portfolio:
    """
    Ребалансировка портфолио в соответствии с торговыми сигналами.
    """
    exchange: BaseExchange

    def __init__(self, exchange):
        self.positions = {}
        self.exchange = exchange
        self.instruments = exchange.instruments
        for symbol, config in self.instruments.items():
            self.positions[symbol] = {"amount": Decimal(0), "signal_price": None}

    def nullify(self):
        for symbol, config in self.instruments.items():
            price = self.exchange.get_price(symbol, "mid")
            self.positions[symbol] = {"amount": Decimal(0), "signal_price": price}

    def rebalance(self, hints):
        """
        Сюда приходят изменения прогноза от стратегий.
        Если изменений не было, то позиция не меняется.
        """

        # TODO: сохранить цену последнего сигнала у каждого элемента портфолио

        for hint in filter(None, hints):

            # TODO: проверить актуальность Hint

            deposit_per_symbol = self.exchange.net_value / len(self.instruments)
            price = self.exchange.get_price(hint.symbol, "mid")
            amount = Decimal(floor(float(deposit_per_symbol) / price))
            position_amount = Decimal(self.positions[hint.symbol]["amount"])
            if hint.signal == Signal.LONG:
                position_amount = +amount
            if hint.signal == Signal.SHORT:
                position_amount = -amount
            if hint.signal == Signal.CLOSE:
                position_amount = Decimal(0)
            self.positions[hint.symbol]["amount"] = position_amount
            self.positions[hint.symbol]["signal_price"] = hint.signal_price

        # print(self.positions)
