import json
import logging
import os.path
from collections import defaultdict
from dataclasses import asdict
from datetime import timezone

log = logging.getLogger("strat_stats")


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class StrategyStats:
    def __init__(self, strategies, portfolio=None):
        self.strategies = strategies
        self.portfolio = portfolio
        self.__stats = defaultdict(list)

    def append(self, strategy, dt):
        profit = self.portfolio.get_profit(strategy) if self.portfolio else 0
        last_bar = asdict(strategy.data[-1])
        last_bar["ts"] = dt_to_ts(dt)
        last_bar["profit"] = profit
        last_bar["strategy"] = type(strategy).__name__
        self.__stats[strategy].append(last_bar)

    def save_ohlc(self, base_dir):
        for strategy in self.strategies:
            strategy_name = type(strategy).__name__
            file_name = f"{strategy.symbol}_{strategy_name}_ohlc.jsonl"
            path = os.path.join(base_dir, file_name)
            data = self.__stats[strategy]
            res = ""
            for line in data:
                res += json.dumps(line, default=str) + "\n"
            with open(path, "w") as f:
                f.write(res)
