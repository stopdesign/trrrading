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
        past_seconds = self.timeframe * length
        # dt = datetime.utcnow() - timedelta(seconds=past_seconds)
        dt = self.exchange.dt_from
        for symbol in self.symbols:
            data = self.exchange.load_tick_data(symbol, dt)
            data = list(filter(lambda x: "price" in x, data))[-length:]
            self.historical[symbol] = data

    # def get_price(self, instrument, side=None):
    #     """
    #     Нужно сделать это по ASK/BID
    #     """
    #     trades = self.historical[instrument]
    #     # print(json.dumps(trades[-5:], indent=2, default=str))
    #     if not trades:
    #         raise Exception(f"No historical for {instrument}")
    #     return Decimal(trades[-1]["price"])

    # def get_price(self, side: str) -> Decimal:
    #     if side == "sell":
    #         price = self.bid[0]["price"]
    #     elif side == "buy":
    #         price = self.ask[0]["price"]
    #     else:
    #         raise ValueError(f"Unknown side: {side}")
    #     return price

    def on_trade(self, trade: dict):
        pass

    def on_quote(self, trade: dict):
        pass
