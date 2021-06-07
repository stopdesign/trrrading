from datetime import datetime, timedelta
from decimal import Decimal
from exchange import ExanteExchange, BacktestExchange


class MarketData:

    def __init__(self, symbols, timeframe, exchange):
        self.symbols = symbols
        self.timeframe = timeframe
        self.exchange = exchange
        self.historical = {}

    def get_historical_data(self, length):
        """
        Тут полное блядство происходит
        """
        for symbol in self.symbols:
            data = self.exchange.load_tick_data(symbol, self.exchange.dt_from)
            data = list(filter(lambda x: "price" in x, data))[-length:]
            self.historical[symbol] = data

    def on_trade(self, trade: dict):
        pass

    def on_quote(self, trade: dict):
        pass
