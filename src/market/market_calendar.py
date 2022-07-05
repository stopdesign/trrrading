from datetime import datetime, timedelta, timezone

import pandas_market_calendars as mcal

IBKR_TO_MCAL = {
    "NASDAQ": "NASDAQ",
    "NYMEX": "NYSE",
    "NYSE": "NYSE",
    "ARCA": "NYSE",
    "GLOBEX": "CME_Rate",
}


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class MarketCalendar:
    def __init__(self, symbols, dt_1, dt_2) -> None:
        self.dt_1 = dt_1 - timedelta(days=15)
        if dt_2:
            self.dt_2 = dt_2 + timedelta(days=15)
        else:
            self.dt_2 = datetime.today() + timedelta(days=300)
        self.grids = self.init_grids(symbols)

    def init_grids(self, symbols):
        res = {}
        for symbol in symbols:
            exchange = IBKR_TO_MCAL[symbol.split(".")[1]]
            if exchange in res:
                continue
            res[exchange] = self.get_grid(exchange)
        return res

    def get_grid(self, exchange):
        """
        Рабочие минутные интервалы от dt_1 до dt_2 в виде списка timestamps.
        """
        calendar = mcal.get_calendar(exchange)

        # Расписание нужной биржи (все доступные интервалы)
        schedule = calendar.schedule(self.dt_1, self.dt_2)  # , market_times="all")

        # Минутные интервалы ETH
        # times = calendar.regular_market_times
        # if "pre" in times and "post" in times:
        #     schedule[["market_open", "market_close"]] = schedule[["pre", "post"]]

        # Минутные интервалы RTH
        open = mcal.date_range(schedule, "1T", closed="left", force_close=1)

        return set(open.view("int64") // 10**9)

    def is_rth(self, symbol, dt) -> bool:
        ex = IBKR_TO_MCAL[symbol.split(".")[1]]
        return dt_to_ts(dt.replace(second=0, microsecond=0)) in self.grids[ex]
