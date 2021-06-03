from decimal import Decimal
from typing import Type, NoReturn
from exchange import BaseExchange
from strategy import BaseStrategy
from util import interval_dt


class Trader:
    def __init__(
        self,
        exchange_class: Type[BaseExchange],
        strategy: BaseStrategy,
        **params
    ):
        # загрузить исторические данные в стратегию
        self.strategy = strategy

        # инициализировать биржу
        self.exchange = exchange_class(

            # callback на события биржи
            on_trade=self.on_trade,
            on_quote=self.on_quote,
            on_interval=self.on_interval,

            # что отслеживать
            symbols=params.get("symbols"),

        )

        self.bots = [
            Bot(ChannelBreakout, symbol="COPX.ARCA", length=320),
            Bot(ChannelBreakout, symbol="URA.ARCA", length=480),
        ]

        self.info = {}

    def start(self, loop):
        # начать слушать обновления биржи
        # или читать данные из архива, если это тест
        self.exchange.start_listen(loop, self.on_trade, self.on_quote, self.on_interval)
        self.exchange.print_final_info()

    def stop(self):
        pass

    def on_quote(self, quote: dict) -> NoReturn:
        # Можно отправить quote в стратегию, если нужно.
        # Биржа уже знает новые quotes
        pass
        # cprint(f"ON_QUOTE {quote}", "white")

    def on_trade(self, trade: dict) -> NoReturn:
        """
        Тут торговля и пирамидинг, если стратегия дала сигнал.
        """
        # cprint(f"ON_TRADE {trade}", "cyan")

        trigger_price = Decimal(trade["price"])
        signal = self.strategy.test(trigger_price)

        position = self.exchange.position

        # Закрыть позицию, если надо
        if position and signal.value and position != signal.value:
            dt = interval_dt(trade)
            self.exchange.close_position(dt)
            position = None

        # Открыть позицию, если надо
        if signal.open and not position:
            dt = interval_dt(trade)
            self.exchange.open_position(dt, signal, 200)

        # Добавить сделку в историю
        # TODO: хорошо бы добавлять сделку в историю до тестирования,
        # TODO: но тогда придется эту сделку игнорировать при анализе
        self.strategy.update_trades(trade)

    def on_interval(self, dt, data):
        """
        Тут собирается статистика. Записывается куда-нибудь, наверное.
        """
        self.info[dt] = data
