import json
import logging
from collections import defaultdict
from dataclasses import asdict
from datetime import timezone

log = logging.getLogger("strat_stats")


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class StrategyStats:
    def __init__(self, strategies, portfolio):
        self.strategies = strategies
        self.portfolio = portfolio
        self.__stats = defaultdict(list)

    def append(self, strategy, dt):
        profit = self.portfolio.get_profit(strategy)
        last_bar = asdict(strategy.data[-1])
        last_bar["ts"] = dt_to_ts(dt)
        last_bar["profit"] = profit
        last_bar["strategy"] = type(strategy).__name__
        self.__stats[strategy].append(last_bar)

    def save_all(self):
        for strategy in self.strategies:
            strategy_name = type(strategy).__name__
            f = open(f"res_{strategy.symbol}_{strategy_name}", "w")
            data = self.__stats[strategy]
            f.write(json.dumps(data, indent=2, default=str))
