import json
from datetime import datetime, timedelta
from decimal import Decimal
from exchange import ExanteExchange


def _():
    pass


class MarketData:

    def __init__(self, symbols, timeframe, post):
        self.symbols = symbols
        self.timeframe = timeframe
        self.exchange = ExanteExchange(
            on_trade=_, on_quote=_, on_interval=_, symbol=""
        )
        self.historical = {}

    def get_historical_data(self, length):
        """
        Тут полное блядство происходит
        """
        past_seconds = self.timeframe * length
        dt = datetime.utcnow() - timedelta(seconds=past_seconds)
        for symbol in self.symbols:
            data = self.exchange.fetch_ohlc_data(symbol, "trades", dt, self.timeframe)
            self.historical[symbol] = []
            for i in data:
                fake_trades = [
                    {"timestamp": i["timestamp"] + 1000, "price": i["low"]},
                    {"timestamp": i["timestamp"] + 2000, "price": i["high"]},
                ]
                self.historical[symbol] += fake_trades

    def get_price(self, instrument, side=None):
        """
        Нужно сделать это по ASK/BID
        """
        trades = self.historical[instrument]
        # print(json.dumps(trades[-5:], indent=2, default=str))
        if trades:
            return Decimal(trades[-1]["price"])
        else:
            return None

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
