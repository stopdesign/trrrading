import logging
from collections import namedtuple
from secrets import token_hex
from typing import Any, Generator, NamedTuple

from pydantic import BaseModel

from trader.data_types import Order, OrderList, Position
from trader.exchange import BaseExchange, Consolidator, Data
from trader.indicator.base import BaseIndicator

log = logging.getLogger("strategy")


class BaseStrategy(BaseModel):
    exchange: BaseExchange
    sid: str
    backtest: bool
    replay: bool
    live: bool

    def __init__(self, **kwargs) -> None:
        kwargs.pop("strategy")
        super().__init__(**kwargs)

        # Названия параметров стратегии
        self.__params = set(self.dict().keys())

        self.log: logging.Logger = logging.getLogger(self.name.lower())

        self.__uid: str = token_hex(2)
        self.__warmed: bool = False

        self.on_start()

        self.log_strategy_info()

    def __str__(self) -> str:
        return str(self.params)

    def log_strategy_info(self) -> None:
        log.info(self.params)

        for data_source in self.data_sources:
            log.info(data_source)

        for consolidator in self.consolidators:
            log.info(consolidator)

        for indicator in self.indicators:
            log.info(indicator)

    def place_order(self, order: Order):
        order.strategy = self
        self.exchange.place_order(order)

    def update_order(self, *args, **kwargs):
        self.exchange.update_order(*args, **kwargs)

    def cancel_order(self, *args, **kwargs):
        self.exchange.cancel_order(*args, **kwargs)

    def set_warmed(self, warmed: bool):
        self.__warmed = bool(warmed)

    @property
    def warmed(self) -> bool:
        return self.__warmed

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def uid(self) -> str:
        return self.__uid

    @property
    def market_system(self) -> str:
        sid = self.sid.split("-")[0]
        return f"{sid}-{self.name}-{self.uid}"

    @property
    def params(self) -> NamedTuple:
        p = self.dict(include=self.__params)
        return namedtuple(self.name, p.keys())(*p.values())

    @property
    def indicators(self) -> Generator[BaseIndicator, None, None]:
        for attr in vars(self).values():
            if isinstance(attr, BaseIndicator):
                yield attr

    @property
    def data_sources(self) -> Generator[Data, None, None]:
        for attr in vars(self).values():
            if isinstance(attr, Data):
                if not isinstance(attr, Consolidator):
                    yield attr

    @property
    def consolidators(self) -> Generator[Consolidator, None, None]:
        for attr in vars(self).values():
            if isinstance(attr, Consolidator):
                yield attr

    @property
    def orders(self) -> OrderList:
        return self.exchange.orders

    @property
    def bars(self) -> dict[str, list]:
        return self.exchange.bars

    @property
    def quotes(self) -> dict[str, dict]:
        return self.exchange.quotes

    @property
    def positions(self) -> dict[str, Position]:
        return self.exchange.positions

    @property
    def account(self) -> dict[str, Any]:
        return self.exchange.account

    def on_start(self) -> None:
        pass

    def on_bar(self, data) -> None:
        pass

    def on_quote(self, data) -> None:
        pass

    def on_tick(self, data) -> None:
        pass

    def on_signal(self, payload: dict) -> None:
        pass

    class Config:
        # Убирает ошибку валидации кастомных классов
        arbitrary_types_allowed = True

        # Позволяет добавлять поля во время работы
        extra = "allow"

        # Убрать некоторые поля из отображений
        fields = {
            "exchange": {"exclude": True},
            "backtest": {"exclude": True},
            "replay": {"exclude": True},
            "live": {"exclude": True},
        }
