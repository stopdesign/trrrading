import json
import logging
import os
import sys
from abc import ABC
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from os.path import abspath
from random import randint
from time import sleep

import pandas as pd
import pandas_market_calendars as mcal
import pytz
import redis
import yaml
from ibapi.common import BarData
from ibapi.contract import Contract
from pandas import date_range
from pandas.tseries.offsets import CustomBusinessDay
from pandas_market_calendars import MarketCalendar
from rich import print
from rich.logging import RichHandler
from rich.text import Text
from rich.traceback import install

p = os.path.abspath("..")
if p not in sys.path:
    sys.path.insert(0, p)

from src.ibkr_api.client import IBThread
from src.ibkr_api.ib_sync import IBSync

# Логгер для этого файла
log = logging.getLogger()

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="%X",
    handlers=[RichHandler(rich_tracebacks=True)],
)

install(show_locals=True)


def ts_to_dt(ts):
    return datetime.utcfromtimestamp(ts)


class IBError(Exception):
    pass


def get_key(instrument):
    # Всё правильно, в базу бары складываются с ключом TRADES
    return "{sid}:TRADES".format(**instrument)


##############################

mask_sun = CustomBusinessDay(weekmask="Sun")  # type: ignore
sundays = date_range("2020-01-01", "2030-01-01", freq=mask_sun)

DT_FMT = "%Y-%m-%d %H:%M:%S"


class CustomCBOT(mcal.exchange_calendar_cme.CMEAgricultureExchangeCalendar):
    regular_market_times = {
        "market_open": ((None, time(19), -1),),  # offset by -1 day
        "market_close": ((None, time(13, 20)),),
        "break_start": ((None, time(7, 45)),),
        "break_end": ((None, time(8, 30)),),
    }

    @property
    def tz(self):
        return pytz.timezone("America/Chicago")


class CustomPaxos(MarketCalendar, ABC):
    regular_market_times = {
        "market_open": ((None, time(16), -1),),  # offset by -1 day
        "market_close": ((None, time(16)),),
    }

    @property
    def name(self):
        return "Paxos"

    @property
    def weekmask(self):
        return "Mon Tue Wed Thu Fri Sun"

    @property
    def special_opens_adhoc(self):
        return [
            (time(3), sundays),
        ]

    @property
    def tz(self):
        return pytz.timezone("US/Eastern")


IBKR_TO_MCAL = {
    "NASDAQ": "NASDAQ",
    "NYMEX": "CMEGlobex_NatGas",
    "NYSE": "NYSE",
    "ARCA": "NYSE",
    "CBOT": "CustomCBOT",
    "CME": "CME_Rate",
    "PAXOS": "CustomPaxos",
}

##############################


def is_redis_available(r):
    try:
        r.ping()
    except (redis.exceptions.ConnectionError, ConnectionRefusedError):
        return False
    return True


class FatalException(Exception):
    pass


class IBSyncData(IBSync):
    """
    Версия IB-клиента для работы с историческими данными.
    """

    def __init__(self, redis_client, instruments):
        super().__init__()
        self.instruments = instruments
        self.prev_bar = {}  # last bar by r_id
        self.request = {}  # request data by r_id
        self.rc = redis_client
        self.connections = {
            "tws": "disconnected",
            "ibkr": "",
        }
        self.response_dt = datetime.min

    def save_bar(self, bar, sid):
        """
        Запись в базу с заменой старых данных.
        """
        # Добавить дату
        ts = int(bar.date)
        dt_str = ts_to_dt(ts).strftime(DT_FMT)
        # bar = dict(dt=dt_str, **bar)

        key = f"{sid}:TRADES"

        bar_data = {
            "dt": dt_str,
            "o": bar.open,
            "h": bar.high,
            "l": bar.low,
            "c": bar.close,
            "v": round(float(bar.volume), 2),
        }
        msg_data = bar_data.copy()
        msg_data["sid"] = sid

        msg_str = json.dumps(msg_data, indent=None, default=str)
        bar_str = json.dumps(bar_data, separators=(",", ":"))

        self.rc.zremrangebyscore(key, ts, ts)
        self.rc.zadd(key, {bar_str: ts})

        a = self.rc.publish(f"{sid}:BARS", msg_str)
        log.info(f"Redis 1-min: {msg_str} - {a}")

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
        # log.info(f"realtime Bar: r_id: {reqId}")
        if req := self.request.get(reqId):
            req["responce_dt"] = datetime.utcnow()

        dt = ts_to_dt(time)
        sid = self.request[reqId]["sid"]

        prices = list(set([open_, high, low, close]))
        for price in prices:
            msg = {
                "dt": dt.strftime(DT_FMT),
                "sid": sid,
                "price": price,
            }
            json_str = json.dumps(msg, indent=None, default=str)
            a = self.rc.publish(f"{sid}:TRADES", json_str)
            log.info(f"Redis 5-sec: {json_str} - {a}")

    def historicalDataUpdate(self, reqId: int, bar: BarData):
        """
        При появлении нового бара отправить старый бар в Redis
        """
        # log.info(f"historical Bar: r_id: {reqId}")
        if req := self.request.get(reqId):
            req["responce_dt"] = datetime.utcnow()

        last_bar = self.prev_bar.get(reqId)
        sid = self.request[reqId]["sid"]

        if last_bar and last_bar.date < bar.date:
            self.save_bar(last_bar, sid)

        self.prev_bar[reqId] = bar

    def managedAccounts(self, accountsList: str):
        super().managedAccounts(accountsList)
        self.connections["tws"] = "connected"
        self.response_dt = datetime.utcnow()

    def currentTime(self, time):
        super().currentTime(time)
        self.connections["tws"] = "connected"
        self.response_dt = datetime.utcnow()

    def connectionClosed(self):
        super().connectionClosed()
        # Все подписки сбрасываются, когда соединение закрывается
        self.connections["tws"] = "disconnected"
        for r_id, sub in self.request.items():
            if not sub.get("canceled"):
                log.error(
                    f"Mark subscription as canceled (closed): {r_id} {sub['sid']}"
                )
                self.request[r_id]["canceled"] = True

    def error(self, reqId: int, errorCode: int, errorString: str, ordRejectJson=""):
        super().error(reqId, errorCode, errorString, ordRejectJson)
        connection_updated = False

        # connected
        if errorCode in [2104, 2106, 2158]:
            source = errorString.split("connection is OK:")[1]
            source = source.strip()
            self.connections[source] = "connected"
            connection_updated = True

        # mass reconnected with data
        if errorCode == 1102:
            txt = errorString.split("connected:")[1]
            for source in txt.split(";"):
                source = source.strip().strip(".")
                self.connections[source] = "connected"
            self.connections["ibkr"] = "connected"
            connection_updated = True

        # reconnected without data
        if errorCode == 1101:
            for key in self.connections.keys():
                self.connections[key] = "disconnected"
            self.connections["ibkr"] = "connected"
            connection_updated = True

        # disconnected
        if errorCode in [2103, 2105, 2157]:
            source = errorString.split("connection is broken:")[1]
            source = source.strip()
            self.connections[source] = "disconnected"
            connection_updated = True

        # inactive
        if errorCode in [2107, 2108]:
            source = errorString.split("upon demand.")[1]
            source = source.strip()
            self.connections[source] = "inactive"
            connection_updated = True

        # connecting (undocumented)
        if errorCode in [2119]:
            source = errorString.split("is connecting:")[1]
            source = source.strip()
            self.connections[source] = "connecting"
            connection_updated = True

        # IB disconnected
        if errorCode in [1100, 2110]:
            self.connections["ibkr"] = "disconnected"
            connection_updated = True

        if connection_updated:
            self.connections["tws"] = "connected"

        # Это приходит без связи с tws
        if errorCode in [502, 504, 1300]:
            for key in self.connections.keys():
                self.connections[key] = "disconnected"
            self.connections["ibkr"] = ""
            connection_updated = True

        # Failed to request live updates (disconnected)
        if errorCode == 10182:
            sub = self.request.get(reqId)
            if sub and not sub.get("canceled"):
                log.error(
                    f"Mark subscription as canceled (code 10182): {reqId} {sub['sid']}"
                )
                sub["canceled"] = True

    def unsubscribe_if_active(self, sid, request_type):
        # Отменить активные подписки данного вида
        for r_id, sub in self.request.items():
            if sub["sid"] == sid and sub["request_type"] == request_type:
                if not sub.get("canceled"):
                    if sub["request_type"] == "real_time_bars":
                        log.warning(f"cancelRealTimeBars: {r_id}")
                        self.cancelRealTimeBars(r_id)
                        self.request[r_id]["canceled"] = True
                    if sub["request_type"] == "historical":
                        log.warning(f"cancelHistoricalData: {r_id}")
                        self.cancelHistoricalData(r_id)
                        self.request[r_id]["canceled"] = True
        sleep(1)

    def subscribe(self, sid, request_type):
        contract = self.contract_for_sid(sid)

        self.unsubscribe_if_active(sid, request_type)

        data_type = "TRADES"
        if request_type == "historical" and contract.secType == "CRYPTO":
            data_type = "MIDPOINT"

        r_id = self.r_id
        self.request[r_id] = {
            "request_type": request_type,
            "contract": contract,
            "sid": sid,
            "data_type": data_type,
            "responce_dt": datetime.max,
        }
        log.info(f"Subscribe: {r_id} {sid} {request_type}")

        if request_type == "real_time_bars":
            self.reqRealTimeBars(r_id, contract, 5, data_type, False, [])

        if request_type == "historical":
            self.reqHistoricalData(
                r_id,
                contract,
                endDateTime="",
                durationStr="300 S",
                barSizeSetting="1 min",
                whatToShow="MIDPOINT",
                useRTH=0,
                formatDate=2,
                keepUpToDate=True,
                chartOptions=[],
            )


class DataMiner:
    rc: redis.Redis
    data_delay: int = 0
    load_limit: int = 1000  # сколько данных максимум забирать из базы
    load_margin: int = 5  # сколько данных в любом случае забирать
    load_history_mode: bool = False

    def __init__(self, ib, rc: redis.Redis) -> None:
        self.rc = rc
        self.ib = ib

    def update_instrument(self, instrument):
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        log.info(f"update_instrument: {instrument}, now: {now}")

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

        exchange = instrument["sid"].split("_")[0]
        exchange = IBKR_TO_MCAL[exchange]

        if exchange == "CustomCBOT":
            calendar = CustomCBOT()
        else:
            calendar = mcal.get_calendar(exchange)

        # Запас, чтобы покрыть 1000 минут с учетом выходных,
        # иначе будет ошибка "indexer is out-of-bounds" в iloc.
        day = datetime.today().date()
        dt_1 = day - timedelta(days=7)
        dt_2 = day + timedelta(days=3)

        # Режим загрузки исторических данных.
        # Здесь нет ограничений по количеству интервалов в прошлое.
        if self.load_history_mode:
            dt_1 = day - timedelta(days=8)

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
        df = df[: as_of - timedelta(seconds=65)]

        if not self.load_history_mode:
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
        db_data = self.rc.zrangebyscore(key, start_ts, 10**10, withscores=True)
        db_data = [[int(d[1]), d[0]] for d in db_data]

        grid["db"] = grid.ts.map(dict(db_data))

        # Статус интервала из базы
        grid["final"] = grid.apply(self._validate_db_bar, axis=1)

        return grid

    # def get_min_editable_bar_ts(self, grid):
    #     """
    #     Интервал не слишком старый для редактирования.

    #     Иногда IBKR меняет старые данные.
    #     После закрытия торговой сессии присылают данные премаркета.
    #     Приходится это игнорировать, т.к. это ломает импорт.
    #     Лимит должен быть меньше, который покрывается API (1000 минут).
    #     """
    #     return int(grid.ts[-1]) - 3600 * 5

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

    def load_ibkr_data(self, instrument: dict, to_load: int, from_ts: int):
        """
        Запросить данные из IBKR, начиная с первого пробела.
        Делается несколько попыток с минимальным перерывом.
        """

        to_load_sec = min(to_load * 60, 3600 * 24)
        duration = f"{to_load_sec} S"

        res = {"data": []}

        print(f"TO LOAD {to_load} {instrument}")

        contract = self.ib.contract_for_sid(instrument["sid"])

        if self.load_history_mode:
            ib_res = []
            duration = "86400 S"
            for i in range(10):
                if ib_res:
                    ts = int(ib_res[0].date)
                    if ts < from_ts:
                        print("DONE", ts, from_ts)
                        break
                    t1 = ts_to_dt(ts)
                    end_dt = t1.strftime("%Y%m%d-%H:%M:%S")
                    print("Loading...", i, end_dt)
                else:
                    end_dt = ""
                ib_res = (
                    self.ib.get_historical_data(
                        contract, end_dt=end_dt, duration=duration
                    )
                    + ib_res
                )
        else:
            ib_res = self.ib.get_historical_data(contract, end_dt="", duration=duration)

        # результат выдать в виде json bar
        ib_data = []
        for line in ib_res:
            bar = {
                "o": line.open,
                "h": line.high,
                "l": line.low,
                "c": line.close,
                "v": round(float(line.volume), 2),
            }
            ib_data.append((int(line.date), bar))

        res["data"] = ib_data
        return res

    def fill_ibkr_data(self, grid: pd.DataFrame, instrument: dict):
        # Найти рабочие интервалы без окончательных данных
        grid_not_final = grid[(grid.final != True) & (grid.open == True)]

        if grid_not_final.empty:
            # Ничего грузить не нужно, сетка заполнена
            log.info(f"Grid is full for {instrument}")
            return grid

        # Посчитать количество интервалов, которые нужно загрузить
        first_not_final_ts = grid_not_final.ts[0]
        to_load = grid[grid.ts >= first_not_final_ts].shape[0]
        to_load = min(to_load + self.load_margin, self.load_limit)

        # print("grid_not_final")
        # print(grid_not_final)

        # Попытка загрузки данных из IBKR
        if res := self.load_ibkr_data(instrument, to_load, first_not_final_ts):
            # TODO: поддержка этого
            # Время задержки данных для аккаунта без подписки
            # self.data_delay = res.json.get("mktDataDelay") or 0

            # if self.data_delay > 0:
            #     log.debug(f"Data delay: {self.data_delay} seconds")
            #     self.data_delay += 100

            # Положить данные IB в сетку, матчинг по полю ts
            grid["ib"] = grid.ts.map(dict(res["data"]))

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

            # if row.ts < self.get_min_editable_bar_ts(grid):
            #     continue

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
                bar = row.ib.copy()
                if late and not self.load_history_mode:
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

            self.save_historical_bar(instrument, bar, row)

    def save_historical_bar(self, instrument, bar, row):
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

        log.info(f"{key} {bar_str}, old: {row.db}")

        self.rc.zremrangebyscore(key, row.ts, row.ts)
        self.rc.zadd(key, {bar_str: row.ts})

        # FIXME: включить отправку бара в события
        # возможно, не в режиме history...
        # key_1 = "{sid}".format(**instrument)
        # bar_str = json.dumps(bar, separators=(",", ":"))
        # self.rc.publish(f"{key_1}:BARS", bar_str)


class Tradis:
    def __init__(self, config: dict) -> None:
        self.redis_config = config["redis"]
        self.gateway = config["gateway"]
        self.instruments = config["instruments"]

        self.subscriptions = []
        for instrument in self.instruments:
            self.subscriptions.append(
                {
                    "sid": instrument["sid"],
                    "request_type": "real_time_bars",
                }
            )
            self.subscriptions.append(
                {
                    "sid": instrument["sid"],
                    "request_type": "historical",
                }
            )

        self.running = True
        self.rc = redis.Redis(**self.redis_config, decode_responses=True)
        self.ib = IBSyncData(self.rc, self.subscriptions)
        self.last_known_connections_status = str(self.ib.connections)

    def request_tws_time(self):
        self.request_time = datetime.utcnow()
        self.ib.reqCurrentTime()

    def print_connection_status(self):
        text = Text("Connections: ")
        for key, value in self.ib.connections.items():
            if value == "connected":
                color = "green"
            elif value == "disconnected":
                color = "red"
            elif value == "connecting":
                color = "cyan"
            elif value == "inactive":
                color = "white"
            else:
                color = "yellow"
            text.append(f"{key} ", style=f"bold {color}")
        print(text)

    def maintain(self):
        """
        Проверка статуса подписок и задержки прихода данных.
        """

        if not self.ib.isConnected():
            return

        for r_id, req in self.ib.request.items():
            now = datetime.utcnow()
            if not req.get("canceled"):
                delay = (now - req["responce_dt"]).total_seconds()
                if delay > 30:
                    sid = req["sid"]
                    rt = req["request_type"]
                    log.warning(f"Stale: {r_id}, {sid}, {rt}, delay: {delay:0.0f}")

        # Нужно взять список того, на что нужно подписаться.
        # Проверить каждый пункт по активным подпискам. Если их нет - подписать.
        for sub in self.subscriptions:
            # поискать такое в активных запросах
            has_active = False
            for req in self.ib.request.values():
                if (
                    req["sid"] == sub["sid"]
                    and req["request_type"] == sub["request_type"]
                    and not req.get("canceled")
                ):
                    has_active = True
            # Если активных запросов нет - подписать
            if not has_active:
                self.ib.subscribe(sub["sid"], sub["request_type"])

        # IB Gateway will not make connections to market data
        # farms until a request is made by the IB client.

        # Проверить синхронизацию времени
        time_diff = abs((self.request_time - self.ib.tws_time).total_seconds())
        if time_diff > 100:
            log.error(f"TWS time out of sync: {time_diff:0.2f} sec")
        elif time_diff > 10:
            log.warning(f"TWS time out of sync: {time_diff:0.2f} sec")

        # Проверить, когда от TWS последний раз приходил ответ
        response_gap = (datetime.utcnow() - self.ib.response_dt).total_seconds()
        if response_gap > 100:
            raise FatalException("tws_delay")
        elif response_gap > 20:  # сильно больше, чем период maintain
            log.warning(f"Large TWS response gap: {response_gap:0.2f} sec")

        # print(f"maintain OK, delay: {delay}")

        # Вывести строку статусов, если с прошлого раза они изменились
        str_connections = json.dumps(self.ib.connections)
        if self.last_known_connections_status != str_connections:
            self.print_connection_status()
            self.last_known_connections_status = str_connections
            self.rc.set("connections", str_connections)

        self.request_tws_time()

    def reset(self):
        # Сбросить все статусы подписки на данные
        pass

    def run(self):
        while self.running:
            try:
                host = self.gateway["host"]
                port = self.gateway["port"]
                self.ib.tws_time = datetime.min
                self.ib.connect(host, port, randint(100, 199))
            except Exception as e:
                log.error(f"TWS connect exception: {e}")
                log.exception(e)
                sleep(5)
                continue

            # Если TWS не запущен или в процессе перезапуска,
            # isConnected вернет false. Повторить попытку через N секунд
            if not self.ib.isConnected():
                log.error(f"TWS not Connected, reconnect in 20 sec")
                sleep(20)
                continue

            # Поток обработки входящих сообщений
            try:
                IBThread(self.ib).start()
            except Exception as e:
                log.error(f"IBThread exception: {e}")
                log.exception(e)
                sleep(5)
                continue

            # You have to make sure the connection has been fully established
            # before attempting to do any requests to the TWS.
            # Failure to do so will result in the TWS closing the connection.
            for _ in range(10):
                if self.ib.nextValidOrderId > 0:
                    log.info(f"TWS Connected, order id: {self.ib.nextValidOrderId}")
                    break
                sleep(0.5)

            # Если не дождались - переконнект
            if not self.ib.nextValidOrderId > 0:
                log.error("No TWS connection, reconnect")
                continue

            self.request_tws_time()
            sleep(1)

            # Сбросить все статусы подписки на данные ???
            # self.reset()

            prev_dt = datetime.min

            while self.ib.isConnected():
                # Проверка связи с Redis
                if not is_redis_available(self.rc):
                    log.error(f"Redis in unavailable")
                    sleep(5)
                    continue

                # Проверки соединения и подписок на данные
                try:
                    sleep(2)  # FIXME: поменять на time from prev run

                    self.maintain()

                    sleep(3)

                    dt = datetime.utcnow()
                    # Это новая минута и прошло достаточно секунд от начала
                    if dt.minute != prev_dt.minute and dt.second > 30:
                        log.info("*** DataMiner update instruments ***")
                        prev_dt = dt
                        try:
                            dm = DataMiner(self.ib, self.rc)
                            for instrument in self.instruments:
                                dm.update_instrument(instrument)
                        except Exception as e:
                            log.error(f"ERROR in DataMiner: {e}")
                            log.exception(e)
                            sleep(1)

                except (KeyboardInterrupt, SystemExit) as e:
                    raise e

                except FatalException as e:
                    log.error(f"Fatal exception: {e}")
                    break

                except Exception as e:
                    # Что-то пошло не так, но соединение активно.
                    log.error(f"Worker exception: {e}")
                    log.exception(e)


if __name__ == "__main__":
    # Загрузка конфига
    config = yaml.full_load(open(abspath("../config/tradis.yaml")))

    tradis = Tradis(config)

    try:
        tradis.run()
    except (KeyboardInterrupt, SystemExit):
        print()
        tradis.ib.disconnect()  # приведет к остановке msg_thread
        log.info(f"DONE")
