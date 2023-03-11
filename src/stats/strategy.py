import json
import logging
import os.path
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone

log = logging.getLogger("strat_stats")


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class StrategyStats:
    """
    История работы стратегии. На каждый бар пишет:
    - ohlc
    - индикаторы
    - profit в разных видах
    """

    def __init__(self, strategies, portfolio=None):
        self.strategies = strategies
        self.portfolio = portfolio
        self.__stats = defaultdict(list)

    def append(self, strategy, dt):
        if self.portfolio:
            cash = float(self.portfolio.target_margin / len(self.portfolio.strategies))
            profit = self.portfolio.get_profit(strategy)
            profit_rel = 100.0 * profit / cash if cash else 0
        else:
            cash = 0
            profit = 0
            profit_rel = 0
        last_bar = asdict(strategy.data[-1])
        last_bar["ts"] = dt_to_ts(dt)
        last_bar["profit"] = profit
        last_bar["profit_rel"] = f"{profit_rel:0.4f}"
        last_bar["strategy"] = strategy.name
        self.__stats[strategy.market_system].append(last_bar)

    def save_ohlc(self, base_dir, min_dt=datetime.min):
        for strategy in self.strategies:
            file_name = f"{strategy.market_system}_ohlc.jsonl"
            path = os.path.join(base_dir, file_name)
            data = self.__stats[strategy.market_system]
            res = ""
            # FIXME: переписать.
            # Смысл в том, что данные добавляются не по порядку,
            # Но сохранить нужно по порядку и не все.
            strat_min_dt = min_dt
            for line in data:
                if line["date"] > strat_min_dt:
                    res += json.dumps(line, default=str) + "\n"
                    strat_min_dt = line["date"]
            with open(path, "w") as f:
                f.write(res)
