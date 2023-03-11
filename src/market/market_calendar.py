from datetime import datetime, timedelta, timezone, time

import pandas_market_calendars as mcal
import pytz


class CustomCBOT(mcal.exchange_calendar_cme.CMEAgricultureExchangeCalendar):
    regular_market_times = {
        "market_open": ((None, time(8,30)),),
        "market_close": ((None, time(13,20)),),
    }

    @property
    def tz(self):
        return pytz.timezone('America/Chicago')


IBKR_TO_MCAL = {
    "NASDAQ": "NASDAQ",
    "NYMEX": "NYSE",
    "NYSE": "NYSE",
    "ARCA": "NYSE",
    "GLOBEX": "CME_Rate",
    "CME": "CME_Rate",
    "CBOT": "CustomCBOT",
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
        if exchange == "CustomCBOT":
            calendar = CustomCBOT()
        else:
            calendar = mcal.get_calendar(exchange)

        # Расписание нужной биржи (все доступные интервалы)
        schedule = calendar.schedule(self.dt_1, self.dt_2)  # , market_times="all")

        # Минутные интервалы ETH
        # times = calendar.regular_market_times
        # if "pre" in times and "post" in times:
        #     schedule[["market_open", "market_close"]] = schedule[["pre", "post"]]

        # Минутные интервалы RTH
        open = mcal.date_range(schedule, "1T", force_close=1)

        # Смещение на одну минуту нужно, чтобы интервал
        # HH:00 был как следующие интервалы этого часа
        res = {dt - 60 for dt in set(open.view("int64") // 10**9)}

        return res

    def is_rth(self, symbol, dt) -> bool:
        ex = IBKR_TO_MCAL[symbol.split(".")[1]]
        return dt_to_ts(dt.replace(second=0, microsecond=0)) in self.grids[ex]
