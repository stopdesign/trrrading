import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import redis
from django.conf import settings
from django.http import HttpResponse

from main.models import Account, Position, Trade
from trader.data_types import Position as tPosition

log = logging.getLogger("views_pnl")


RANGE = 15


class PerformanceReport:
    account: Account
    rc: redis.Redis

    holiday_gap_days = 10

    @classmethod
    def adjust_price(cls, contract, price) -> Decimal:
        return Decimal(price) / contract.price_magnifier * contract.multiplier

    def __init__(self, redis_client, account_id):
        self.rc = redis_client
        a = Account.objects.get(pk=account_id)

        self.now = datetime.now().replace(microsecond=0).astimezone(ZoneInfo("UTC"))

        # Calculate the start date by going back to the most recent Sunday
        prev_sun = self.now - timedelta(days=self.now.weekday() + 1)
        prev_sun = prev_sun.replace(hour=0, minute=0, second=0, microsecond=0)

        # Начало первой недели отчета
        dt_1 = prev_sun - timedelta(weeks=RANGE)

        # Запас на праздники и UTC
        dt_0 = dt_1 - timedelta(days=self.holiday_gap_days)

        # Позиции данного аккаунта сейчас по всем контрактам
        positions = Position.objects.filter(account=a).prefetch_related("contract")

        # Одним запросом достаю сделки данного аккаунта за весь период
        trades = Trade.objects.order_by("time").prefetch_related("order__contract")
        trades = trades.filter(account=a, time__gt=dt_1)

        self.trades_by_sid = defaultdict(list)
        for trade in trades:
            self.trades_by_sid[trade.order.contract.sid].append(trade)

        # Контракты, которые есть в сделках или позициях
        contracts = {t.order.contract for t in trades}
        contracts.update({p.contract for p in positions})
        self.contracts = contracts

        # Positions from contracts with trades
        self.positions_by_sid = {c.sid: 0 for c in self.contracts}

        # Current positions from DB
        self.positions_by_sid.update({p.contract.sid: p.amount or 0 for p in positions})

        # Cache OHLC daily data from dt_0
        self.ohlc_data_by_sid = self.preload_ohlc(dt_0)

    def preload_ohlc(self, dt) -> defaultdict:
        """
        Загрузить цены по всем нужным контрактам, рассовать по дням
        """
        res = defaultdict(dict)
        score_1 = datetime.strftime(dt.astimezone(ZoneInfo("UTC")), "%Y%m%d")
        score_2 = "20380101"
        for contract in self.contracts:
            key = f"{contract.sid}:DAILY"
            if ohlc_data := self.rc.zrangebyscore(key, score_1, score_2):
                for ohlc_str in ohlc_data:
                    ohlc = json.loads(ohlc_str)
                    res[contract.sid][ohlc["d"]] = ohlc
        return res

    def get_ohlc(self, sid, dt) -> dict:
        """
        Daily OHLC за данное число или ближайшее предыдущее значение
        в пределах 10 дней (чтобы функция что-то вернула даже в выходной)
        """
        for i in range(10):
            key = datetime.strftime(dt - timedelta(days=i), "%Y-%m-%d")
            if ohlc := self.ohlc_data_by_sid[sid].get(key):
                return ohlc
        raise Exception(f"No price for {sid} at {dt}")

    def pnl_report(self, contract) -> list:
        contract_weekly_profit = []

        # Calculate the start date by going back to the most recent Sunday
        prev_sun = self.now - timedelta(days=self.now.weekday() + 1)
        prev_sun = prev_sun.replace(hour=0, minute=0, second=0, microsecond=0)

        # Начало первой недели
        w_cur = prev_sun - timedelta(weeks=RANGE)

        # Фильтр нужных сделок по времени
        trades = [t for t in self.trades_by_sid[contract.sid] if t.time >= w_cur]

        position_now = self.positions_by_sid[contract.sid]

        # Не было сделок и нет открытой позиции - пропустить
        if not len(trades) and not position_now:
            return contract_weekly_profit

        # Размотать сделки обратно и посчитать позицию в начале
        cur_pos = position_now - sum([t.signed_amount for t in reversed(trades)])

        while w_cur <= prev_sun:
            # print(f"\nw_cur {w_cur.date()}")
            try:
                res, cur_pos = self.contract_weekly_pnl(
                    contract, trades, cur_pos, w_cur
                )
                contract_weekly_profit.append(res)
            except Exception as e:
                log.error(e)
                contract_weekly_profit.append(
                    {
                        "week": str(w_cur.date()),
                        "trades": 0,
                        "commission": 0,
                        "pnl": 0,
                        "error": "no price",
                    }
                )
            w_cur += timedelta(weeks=1)

        assert not trades

        return contract_weekly_profit

    def contract_weekly_pnl(self, contract, trades, cur_pos, w_cur):
        # TODO: вынести подсчет trades и comm в класс tPosition

        w_cur_end = min(w_cur + timedelta(weeks=1), self.now)

        w_comm = Decimal(0)
        w_trades = 0

        t_pos = tPosition(contract.sid)
        if cur_pos:
            ohlc = self.get_ohlc(contract.sid, w_cur)
            price = self.adjust_price(contract, ohlc["c"])
            t_pos.update(Decimal(cur_pos), price)

            # Учесть сделку и выбросить из списка
        while trades and trades[0].time < w_cur_end and trades[0].time >= w_cur:
            trade = trades.pop(0)
            cur_pos += trade.signed_amount
            price = self.adjust_price(contract, trade.price)
            t_pos.update(Decimal(cur_pos), price)
            w_trades += 1
            w_comm += trade.commission

        # Если в конце недели есть позиция - посчитать Market Value
        if cur_pos:
            ohlc = self.get_ohlc(contract.sid, w_cur_end)
            price = self.adjust_price(contract, ohlc["c"])
            t_pos.update(Decimal(0), price)

        res = {
            "week": str(w_cur.date()),
            "trades": w_trades,
            "commission": float(round(w_comm, 2)),
            "pnl": float(round(t_pos.profit - w_comm, 2)),
        }

        return res, cur_pos

    def generate(self) -> dict:
        res = {}
        for contract in self.contracts:
            amount = self.positions_by_sid[contract.sid]
            avg_price = None
            if contract.sec_type in ["CASH", "CRYPTO"]:
                if amount != 0:
                    res[contract.sid] = {
                        "sid": contract.sid,
                        "sec_type": contract.sec_type,
                        "amount": amount,
                        "avg_price": avg_price,
                        "pnl": [],
                    }
            else:
                res[contract.sid] = {
                    "sid": contract.sid,
                    "sec_type": contract.sec_type,
                    "amount": amount,
                    "avg_price": avg_price,
                }
                res[contract.sid]["pnl"] = self.pnl_report(contract)
        return res


def pnl_report(request):
    redis_client = redis.Redis(
        host=settings.TRADIS_HOST,
        port=settings.TRADIS_PORT,
        db=settings.TRADIS_DB,
        decode_responses=True,
    )

    account_id = request.GET.get("account")

    report = PerformanceReport(redis_client=redis_client, account_id=account_id)
    res = report.generate()

    content = json.dumps(res, default=str, indent=2)

    return HttpResponse(content, content_type="application/json")
