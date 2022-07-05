import json
import logging
from math import floor
from decimal import Decimal, ROUND_DOWN
from data_types import Margin, Position
from main.views import dt_to_ts
from strategy import Signal
from trader import Exchange
from termcolor import colored

log = logging.getLogger("portfolio")


class Portfolio:
    """
    Ребалансировка портфолио в соответствии с торговыми сигналами.
    """

    exchange: Exchange
    margin = Margin(long=0.25, short=0.3)

    def __init__(self, exchange, strategies, target_margin: Decimal):
        self.__positions = {}
        self.events = {}
        self.exchange = exchange
        self.strategies = strategies
        self.target_margin = target_margin
        self.total_profit = Decimal(0)
        for strategy in self.strategies:
            self.__positions[strategy] = Position(strategy.symbol)
            self.events[strategy] = []

    def get_amount(self, strategy) -> Decimal:
        return self.__positions[strategy].amount

    def set_initial_amount(self, strategy, amount, price=Decimal("nan")):
        self.__positions[strategy].update(amount, price)

    def get_profit(self, strategy):
        net = Decimal(0)
        position = self.__positions[strategy]
        if position.amount:
            side = "sell" if position.amount > 0 else "buy"
            price = self.exchange.get_price(strategy.symbol, side)
            net += position.amount * (price - position.avg_price)
        net += position.profit
        return int(net)

    def get_total_amount(self, symbol) -> Decimal:
        """
        Возвращает количество данного инструмента во всем стратегиям.
        """
        amount = Decimal(0)
        for strategy in self.strategies:
            if strategy.symbol == symbol:
                amount += self.__positions[strategy].amount
        return amount

    def get_virtual_net_value(self) -> Decimal:
        net = Decimal(0)
        for strategy in self.strategies:
            position = self.__positions[strategy]
            if position.amount:
                side = "sell" if position.amount > 0 else "buy"
                price = self.exchange.get_price(strategy.symbol, side)
                net += position.amount * (price - position.avg_price)
            net += position.profit
        return net.quantize(Decimal("0.01"), ROUND_DOWN)

    def get_info(self):
        txt = ""
        for strategy in self.strategies:
            txt += f"{strategy}, {self.__positions[strategy].profit:+0.2f}\n"
        return txt.strip()

    def rebalance(self, hints):
        """
        Сюда приходят изменения прогноза от стратегий.
        Если изменений не было, то позиция не меняется.

        Сигналы преобразуются в количество акций с учетом
        доступной стратегии суммы и маржинальных требований.
        """
        for hint in filter(None, hints):

            cash_per_strategy = self.target_margin / len(self.strategies)

            # TODO: подсчет позиции с учетом magrin level

            amount = Decimal("nan")
            price = Decimal("nan")

            side = hint.signal.side

            if hint.signal == Signal.LONG:
                price = self.exchange.get_price(hint.symbol, "buy")
                amount = +Decimal(floor(cash_per_strategy / price))

            if hint.signal == Signal.SHORT:
                price = self.exchange.get_price(hint.symbol, "sell")
                amount = -Decimal(floor(cash_per_strategy / price))

            if hint.signal == Signal.CLOSE:
                cur_amount = self.__positions[hint.strategy].amount
                side = "sell" if cur_amount > 0 else "buy"
                price = self.exchange.get_price(hint.symbol, side)
                amount = Decimal(0)

            if hint.signal == Signal.PASS:
                log.warning(f"Maybe there was no signal? {hint}")

            assert not price.is_nan(), f"no price for signal {hint.signal}"
            assert not amount.is_nan()

            profit = self.__positions[hint.strategy].update(amount, price)
            self.total_profit += profit

            data = {
                'dt': hint.signal_dt,
                'time': dt_to_ts(hint.signal_dt),
                'side': side,
                'amount': abs(amount),
                'profit': profit,
                'price': price,
            }
            self.events[hint.strategy].append(data)

            profit_colored = ""
            if profit > 0:
                profit_colored = colored(f"{profit:+0.2f}", "green")
            elif profit < 0:
                profit_colored = colored(f"{profit:+0.2f}", "red")
            else:
                profit_colored = colored("~0.00", "blue")

            log.info(
                f"{hint}, amount: {amount:+0.0f}, "
                f"profit: {profit_colored}, "
                f"Σ: {self.total_profit:+0.2f}"
            )
