import logging

from exchange import BaseExchange

log = logging.getLogger("execution")


class Execution:
    """
    Применение Target Positions к реальному миру.
    """
    exchange: BaseExchange

    def __init__(self, exchange, portfolio):
        self.exchange = exchange
        self.target_positions = portfolio
        self.actual_positions = self.exchange.get_positions()

    def apply_targets(self, dt):

        # что на самом деле есть в портфолио
        self.actual_positions = self.exchange.get_positions()

        for instrument in self.exchange.instruments:
            actual = self.actual_positions.get(instrument, {}).get("amount", 0)
            target = self.target_positions.positions.get(instrument, 0)

            if actual == target:
                pass
            elif actual < target:
                delta = target - actual
                # print("buy", delta)
                self.exchange.trade("buy", delta, instrument, dt, None)
            elif actual > target:
                delta = actual - target
                # print("sell", delta)
                self.exchange.trade("sell", delta, instrument, dt, None)
