class BaseStrategy:

    interval_size = 60

    def __init__(self, **params):
        super().__init__()
        self.length = params.pop("length")
        self.params = params
        self.data = []
        self.historical = []
        self.on_start()

    def __str__(self):
        return f"<{self.__class__.__name__} length={self.length}>"

    def add_to_historical(self, data):
        self.historical += data

    def on_start(self):
        pass

    def on_bar(self, data):
        pass

    def on_quote(self, data):
        pass

    def on_trade(self, data):
        pass
