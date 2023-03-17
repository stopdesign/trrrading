"""
Скрипт подписывается на исторические данные в TWS и фигачит их в Redis.
"""

from decimal import Decimal
import json
import logging
from datetime import datetime, timedelta, timezone
from os.path import abspath
from time import sleep

import coloredlogs
import pandas as pd
import pandas_market_calendars as mcal
import redis
import yaml
from termcolor import colored, cprint

from rich import print
from rich.logging import RichHandler

import os, sys

p = os.path.abspath("..")
if p not in sys.path:
    sys.path.insert(0, p)

from src.ibkr_api.client import IbContract, IBThread
from src.ibkr_api.ib_sync import IBSync

from ibapi.common import TickerId, BarData, RealTimeBar

# # Логгер для этого файла
# log = logging.getLogger("market_data")
# log.setLevel(logging.INFO)

# coloredlogs.install(
#     "INFO", fmt="%(asctime).19s • %(levelname).1s • %(name)s • %(message)s"
# )

# Логгер для этого файла
log = logging.getLogger()

# log.setLevel(logging.INFO)

# coloredlogs.install(
#     "INFO", fmt="%(asctime).19s • %(levelname).1s • %(name)s • %(message)s"
# )

def ts_to_dt(ts):
    return datetime.utcfromtimestamp(ts)

def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="%X",
    handlers=[RichHandler(rich_tracebacks=True)],
)


# pd.options.display.width = 300
# pd.options.display.max_rows = 1500
# pd.options.display.max_columns = None
# pd.options.display.max_colwidth = None
# pd.options.display.expand_frame_repr = False


DT_FMT = "%Y-%m-%d %H:%M:%S"

IBKR_TO_MCAL = {
    "NASDAQ": "NASDAQ",
    "NYMEX": "NYSE",
    "NYSE": "NYSE",
    "ARCA": "NYSE",
    "GLOBEX": "CME_Rate",
}


class IBError(Exception):
    pass


def get_key(instrument):
    # Всё правильно, в базу бары складываются с ключом TRADES
    return "{symbol}.{exchange}:TRADES".format(**instrument)


class DataMiner:
    rc: redis.Redis
    data_delay: int = 0
    load_margin: int = 100
    load_limit: int = 1000

    def __init__(self, ib, rc: redis.Redis) -> None:
        self.rc = rc
        self.ib = ib
        self.ib.load_session()

    def update_instrument(self, instrument):

        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        # Сделать минутную сетку
        grid = self.get_grid(instrument, as_of=now)

        # Положить в неё данные из базы.
        grid = self.load_redis_data(grid, instrument)

        # Заполнить пробелы данными из IBKR
        grid = self.fill_ibkr_data(grid, instrument)

        # Сравнить данные из базы и из IBKR, обновить при различиях.
        self.update_db(grid, instrument)

    def get_grid(self, instrument, as_of):
        """
        Минутная сетка с разметкой основной и расширенной биржевой сессии.
        Возвращает сетку, где есть N рабочих минут до now включительно.
        Нерабочие минуты включаются в сетку, но их количество не учитывается.
        """
        working_minutes_cnt = self.load_limit

        exchange = instrument["exchange"]
        calendar = mcal.get_calendar(IBKR_TO_MCAL[exchange])

        # Запас, чтобы покрыть 1000 минут с учетом выходных,
        # иначе будет ошибка "indexer is out-of-bounds" в iloc.
        day = datetime.today().date()
        dt_1 = day - timedelta(days=7)
        dt_2 = day + timedelta(days=3)

        # Минутная сетка шкалы времени
        df = pd.DataFrame(pd.date_range(dt_1, dt_2, freq="1T", tz="UTC"))

        # Расписание нужной биржи (все доступные интервалы)
        schedule = calendar.schedule(dt_1, dt_2, market_times="all")

        # Минутные интервалы ETH
        times = calendar.regular_market_times
        if "pre" in times and "post" in times:
            schedule[["market_open", "market_close"]] = schedule[["pre", "post"]]
        open = mcal.date_range(schedule, "1T", force_close=1)

        # Смещение на одну минуту нужно, чтобы интервал
        # HH:00 был как следующие интервалы этого часа
        df["open"] = df[0].isin(open).shift(-1)

        df.set_index(0, inplace=True)

        # Обрезать всё после now.
        # Делается запас, чтобы не обрабатывалась открытая минута.
        df = df[:as_of - timedelta(seconds=65)]

        # Нужное количество интервалов (с конца), где биржа открыта
        start_dt = df[df["open"]].iloc[-working_minutes_cnt].name
        df = df.loc[start_dt:]

        # Unix timestamp, seconds
        df["ts"] = df.index.view("int64") // 10**9

        df["ib"] = None

        return df

    def _validate_db_bar(self, bar):
        """
        Хорошим считается бар, в котором есть dt и цена, флаг closed или empty.
        """
        s = bar.db if type(bar.db) is str else ""
        return '{"dt":' in s and ('"o":' in s or '"closed":' in s or '"empty":' in s)

    def load_redis_data(self, grid: pd.DataFrame, instrument: dict):
        """
        Данные загружаются из Redis и складываются в поля сетки.
        """
        start_ts = int(grid.ts[0])

        key = get_key(instrument)
        db_data = self.rc.zrangebyscore(key, start_ts, 10**10, withscores=1)
        db_data = [[int(d[1]), d[0].decode()] for d in db_data]

        grid["db"] = grid.ts.map(dict(db_data))

        # Статус интервала из базы
        grid["final"] = grid.apply(self._validate_db_bar, axis=1)

        return grid

    def get_min_editable_bar_ts(self, grid):
        """
        Интервал не слишком старый для редактирования.

        Иногда IBKR меняет старые данные.
        После закрытия торговой сессии присылают данные премаркета.
        Приходится это игнорировать, т.к. это ломает импорт.
        Лимит должен быть меньше, который покрывается API (1000 минут).
        """
        return int(grid.ts[-1]) - 3600 * 5

    def validate_ibkr_res(self, res):
        """
        Валидация ответа.
        """
        if res.error or res.exception:
            raise IBError(res.error or "exception")
        if not res.json:
            raise IBError("no_json")
        if not res.json.get("data"):
            raise IBError("no_data")

    def load_ibkr_data(self, instrument: dict, to_load: int):
        """
        Запросить данные из IBKR, начиная с первого пробела.
        Делается несколько попыток с минимальным перерывом.
        """
        conid = instrument["conid"]
        period = f"{to_load}min"

        res = None

        for _ in range(3):
            try:
                res = self.ib.market_data.history(conid, period=period, rth=False)
                self.validate_ibkr_res(res)
                log.debug("Success")
                break
            except IBError as e:
                res = None
                log.error(f"IB data error: {instrument}, {e}")
            except Exception as e:
                res = None
                log.error(f"IB API exception: {instrument}")
                log.exception(e)
            log.warning("Retry in 3 seconds...")
            sleep(3)
            self.ib.load_session()

        return res

    def fill_ibkr_data(self, grid: pd.DataFrame, instrument: dict):

        # Найти рабочие интервалы без окончательных данных
        grid_not_final = grid[(grid.final != True) & (grid.open == True)]

        if grid_not_final.empty:
            # Ничего грузить не нужно, сетка заполнена
            return grid

        # Посчитать количество интервалов, которые нужно загрузить
        first_not_final_ts = grid_not_final.ts[0]
        to_load = grid[grid.ts >= first_not_final_ts].shape[0]
        to_load = min(to_load + self.load_margin, self.load_limit)

        # Попытка загрузки данных из IBKR
        if res := self.load_ibkr_data(instrument, to_load):

            # Время задержки данных для аккаунта без подписки
            self.data_delay = res.json.get("mktDataDelay") or 0

            if self.data_delay > 0:
                log.debug(f"Data delay: {self.data_delay} seconds")
                self.data_delay += 100

            ib_data = [[bar["t"] // 1000, bar] for bar in res.json["data"]]

            # Положить данные IB в сетку, матчинг по полю ts
            grid["ib"] = grid.ts.map(dict(ib_data))

        return grid

    def _empty_bar_fsm(self, empty_bar_state, row):
        """
        Empty bar validation FSM.
        """
        if row.ib:
            empty_bar_state = "has_data"
        if empty_bar_state and not row.ib:
            if not row.open:
                empty_bar_state = "closed"
            elif empty_bar_state == "closed":
                empty_bar_state = "empty_ok"
        return empty_bar_state

    def update_db(self, grid: pd.DataFrame, instrument: dict):
        """
        closed — биржа закрыта
        empty  — биржа открыта, но сделок сегодня еще не было
        fix    — интервал был перезаписан
        error  — ошибка
        """
        # Замена всякой хуйни на None
        grid = grid.where(pd.notnull(grid), None)

        # FSM for possibility of empty bar state
        empty_bar_state = None

        for row in grid.itertuples():

            # Empty bar FSM needs full grid (with final bars)
            empty_bar_state = self._empty_bar_fsm(empty_bar_state, row)

            if row.ts < self.get_min_editable_bar_ts(grid):
                continue

            if row.final:
                continue

            if not row.open and row.ib:
                log.error(f"IBKR bar data on closed market {row.ib}")

            late = row.ts < (grid.ts[-1] - self.data_delay)

            if not row.open:
                # Биржа закрыта
                bar = {"closed": 1}
            elif row.ib:
                # Есть нормальный интервал
                b = row.ib
                bar = dict(o=b["o"], h=b["h"], l=b["l"], c=b["c"], vol=b["v"])
                if late:
                    bar["late"] = 1
            elif empty_bar_state == "empty_ok":
                # Корректные условия для EMPTY
                bar = {"empty": 1}
            else:
                # Данные должны быть, но их нет
                if late and empty_bar_state:
                    if empty_bar_state:
                        bar = {"error": 1}
                    else:
                        # похоже, интервал слишком старый и не влез в лимит
                        log.debug(f"Skip old empty bar: {row}")
                        continue
                else:
                    bar = {"delay": 1}

            if row.db and type(row.db) is str:
                if "error" in bar:
                    log.debug(f"Don't rewrite with error. Old: {row.db}")
                    continue
                elif "delay" in row.db:
                    log.debug(f"Don't mark delay as a fix. Old: {row.db}")
                else:
                    bar["fix"] = 1

            self.save_bar(instrument, bar, row)

    def save_bar(self, instrument, bar, row):
        """
        Запись в базу с заменой старых данных.
        """
        # Добавить дату
        dt_str = row.Index.strftime(DT_FMT)
        bar = dict(dt=dt_str, **bar)

        key = get_key(instrument)
        bar_str = json.dumps(bar, separators=(",", ":"))

        # Не сохранять такую же строку повторно (не учитывая флаг fix)
        # FIXME: выглядит тупо
        if str(row.db).replace(',"fix":1', "") == bar_str.replace(',"fix":1', ""):
            return

        log.info(colored(f"{key} {bar_str}, old: {row.db}", "white"))

        self.rc.zremrangebyscore(key, row.ts, row.ts)
        self.rc.zadd(key, {bar_str: row.ts})

        symbol = "{symbol}.{exchange}".format(**instrument)
        bar["conid"] = instrument["conid"]
        bar["symbol"] = symbol
        bar_str = json.dumps(bar, separators=(",", ":"))
        self.rc.publish(f"{symbol}:BARS", bar_str)


def main(ib: IBSync, redis_client, instruments):

    prev_dt = datetime(2000, 1, 1)
    while dt := datetime.utcnow():

        if not (dt.minute != prev_dt.minute and dt.second > 10):
            sleep(1)
            continue

        prev_dt = dt
        try:
            dm = DataMiner(ib, redis_client)
            for instrument in instruments:
                dm.update_instrument(instrument)
        except Exception as e:
            log.error(cprint(f"ERROR in DataMiner: {e}", "red"))
            log.exception(e)
            sleep(1)

        log.info("Done\n")


class IBSyncData(IBSync):

    def __init__(self, redis_client, instruments):
        super().__init__()
        self.instruments = instruments
        self.prev_bar = {}  # last bar by r_id
        self.request = {}  # request data by r_id
        self.rc = redis_client

    def save_bar(self, contract, bar):
        """
        Запись в базу с заменой старых данных.
        """
        # Добавить дату
        ts = int(bar.date)
        dt_str = ts_to_dt(ts).strftime(DT_FMT)
        # bar = dict(dt=dt_str, **bar)

        sid = "CME_MES_2306"
        key = f"{sid}:TRADES"  # get_key(contract)

        msg = {
            "dt": dt_str,
            "sid": sid,
            "o": bar.open,
            "h": bar.high,
            "l": bar.low,
            "c": bar.close,
            "v": round(float(bar.volume), 2),
        }

        bar_str = json.dumps(msg, indent=None, default=str)

        self.rc.zremrangebyscore(key, ts, ts)
        self.rc.zadd(key, {bar_str: ts})

        a = self.rc.publish(f"{sid}:BARS", bar_str)
        log.info(f"Redis: {bar_str} - {a}")

    def realtimeBar(
        self,
        reqId: int,
        time: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: Decimal,
        wap: Decimal,
        count: int,
    ):
        """
        5-sec real-time OHLC bars.
        """
        dt = ts_to_dt(time)

        contract = self.request[reqId]["contract"]
        sid = "CME_MES_2306"

        prices = list(set([open_, high, low, close]))
        for price in prices:
            msg = {
                "dt": dt.strftime(DT_FMT),
                "sid": sid,
                "price": price,
            }
            json_str = json.dumps(msg, indent=None, default=str)
            a = redis_client.publish(f"{sid}:TRADES", json_str)
            log.info(f"Redis: {json_str} - {a}")

    def historicalDataUpdate(self, reqId: int, bar: BarData):
        """
        При появлении нового бара отправить старый бар в Redis
        """
        # log.info(bar)

        last_bar = self.prev_bar.get(reqId)
        contract = self.request[reqId]["contract"]

        if last_bar and last_bar.date < bar.date:
            self.save_bar(contract, last_bar)

        self.prev_bar[reqId] = bar

    def subscribe(self):
        print(instruments)

        symbol = "MES"
        exchange = "CME"
        contract = IbContract(symbol, secType="CONTFUT", exchange=exchange)

        cd = self.get_contract_details(contract)
        contract = cd[0].contract

        # self.reqMarketDataType(3)

        # Это самое удобное
        r_id = self.r_id
        self.request[r_id] = {
            "request_type": "real_time_bars",
            "contract": contract,
            "data_type": "TRADES",
        }
        self.reqRealTimeBars(r_id, contract, 5, "TRADES", False, [])


        # При открытии нового бара передавать предыдущий в redis
        r_id = self.r_id
        self.request[r_id] = {
            "request_type": "historical",
            "contract": contract,
            "data_type": "TRADES",
        }
        self.reqHistoricalData(
            r_id,
            contract,
            endDateTime="",
            durationStr="600 S",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=0,
            formatDate=2,
            keepUpToDate=True,
            chartOptions=[],
        )



if __name__ == "__main__":
    dt = datetime.now()

    # Загрузка конфига
    config = yaml.full_load(open(abspath("../config/tradis.yaml")))

    instruments = config["instruments"]

    redis_config = config["redis"]
    ib_params = config["gateway"]

    redis_client = redis.Redis(socket_timeout=5, **redis_config)

    app = IBSyncData(redis_client, instruments)

    try:
        app.connect(ib_params["host"], ib_params["port"], ib_params["client_id"])

        # Endless message loop
        thread = IBThread(app)
        thread.start()

        # Wain for connection
        while True:
            if isinstance(app.nextValidOrderId, int):
                log.info(f"IB Connected")
                break
            sleep(0.5)

        app.subscribe()

        sleep(100000)

    except (KeyboardInterrupt, SystemExit):
        print()
        log.info("Stop\n")

    finally:
        app.disconnect()

    # try:
    #     main(ib, redis_client, instruments)
    # except KeyboardInterrupt:
    #     pass

    print(f"\nDone in {str(datetime.now() - dt)[:-7]}")
