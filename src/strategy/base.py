from collections import defaultdict
from util import trades_to_ohlc


class BaseStrategy:

    interval_size = 60

    def __init__(self):
        self.historical = []

    def add_to_historical(self, data):
        self.historical += data
