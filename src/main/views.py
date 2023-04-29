import glob
import json
import os.path
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import orjson
import requests
from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render

from main.models import Account, Contract, Order, Position, Trade


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


RES_DIR = os.path.abspath(os.path.join(settings.BASE_DIR, "../../res"))


def dashboard(request):
    accounts = list(Account.objects.order_by("uid").values("id", "uid"))
    for account in accounts:
        uid = account["uid"]
        account["uid"] = uid[:4] + "***" + uid[-2:]
    return render(request, "react_dashboard.html", {"accounts": accounts})


def backtest(request):
    results = list(sorted(next(os.walk(RES_DIR))[1], reverse=True))[:5]
    context = {
        "backtest_results": results,
    }
    return render(request, "backtest_chart.html", context)


def bt_ohlc(request):
    symbol = request.GET.get("symbol")
    result_id = symbol[:17]
    strategy_id = symbol.split("#")[0][18:]
    ohlc_file = f"{RES_DIR}/{result_id}/{strategy_id}-ohlc.jsonl"
    content = "[" + open(ohlc_file).read().replace("\n", ",\n").strip(",\n") + "]"
    return HttpResponse(content, content_type="application/json")


def bt_results(request):
    results = list(sorted(next(os.walk(RES_DIR))[1], reverse=True))[:20]
    res = {
        "results": sorted(results, reverse=True),
    }
    context = json.dumps(res, indent=None, default=str)
    return HttpResponse(context, content_type="application/json")


def bt_strategies(request):
    res = []
    result = request.GET.get("result", "")
    files = glob.glob(f"{RES_DIR}/{result}/*-ohlc.jsonl")
    for file in files:
        file = os.path.basename(file)
        split = file.split("-")
        instrument, strategy, var, _ = split
        res.append(
            {
                "id": f"{instrument}-{strategy}-{var}",
                "strategy": strategy,
                "instrument": instrument,
            }
        )
    res = sorted(res, key=lambda r: (r["instrument"], r["strategy"]))
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def bt_meta(request):
    result_id = request.GET.get("result")
    meta_file = f"{RES_DIR}/{result_id}/meta.json"
    try:
        content = open(meta_file).read()
    except:
        content = "{}"
    return HttpResponse(content, content_type="application/json")


def bt_events(request):
    result_id = request.GET.get("result")
    strategy_id = request.GET.get("strategy")

    ohlc_file = f"{RES_DIR}/{result_id}/{strategy_id}-events.jsonl"

    content = open(ohlc_file).read()

    if content:
        data = orjson.loads("[" + content.strip().replace("\n", ",") + "]")
    else:
        data = []

    res = []

    for i, order in enumerate(data):
        res.append(
            {
                "id": i,
                "order_id": i,
                "local_id": i,
                "symbol": strategy_id,
                "amount": order["amount"],
                "filled": order["amount"],
                "status": "filled",
                "price": order["price"],
                "profit": order["profit"],
                "side": order["side"],
                "signal": order["side"],
                "time": order["time"],
                "created": order["dt"],
            }
        )
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def account(request):
    account_id = request.GET.get("account", 0)
    account = Account.objects.get(id=account_id)

    try:
        # FIXME: убрать хардкодинг адреса здесь и в orders.js
        res = requests.get("http://10.0.10.1:8080/connections", timeout=1)
        connections = res.json()
        connections = list(connections.items())
    except:
        connections = []

    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc)
    update_delay = (utc_now - account.updated_at).total_seconds()

    res = {
        "uid": account.uid,
        "daily_pnl": account.daily_pnl,
        "unrealized_pnl": account.unrealized_pnl,
        "realized_pnl": account.realized_pnl,
        "net_value": account.net_value,
        "margin_used": account.margin_used,
        "cash_value": account.cash_value,
        "ex_liq_sec": account.ex_liq_sec,
        "ex_liq_com": account.ex_liq_com,
        "connections": connections,
        "update_delay": update_delay,
    }
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def positions(request):
    account_id = request.GET.get("account", 0)
    res = []

    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc)
    too_old = utc_now - timedelta(days=1)

    positions = Position.objects.filter(account_id=account_id)
    positions = positions.order_by("contract__sec_type", "contract__sid")
    positions = positions.prefetch_related()
    for position in positions:
        # Позиция нулевая и давно не обновлялась
        if not bool(position.amount) and position.updated_at < too_old:
            continue
        if position.avg_price:
            if position.contract.sec_type in [Contract.Type.cash, Contract.Type.crypto]:
                price = f"{position.avg_price:0.4f}"
            else:
                price = f"{position.avg_price:0.2f}"
        else:
            price = "--"
        sid = position.contract.sid
        name = (sid.split("_", 1)[1]).replace("_", " ")
        res.append(
            {
                "symbol": sid,
                "name": name,
                "amount": position.amount,
                "avg_price": price,
                "unrealized_pnl": position.unrealized_pnl,
                "updated": position.updated_at,
            }
        )
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def orders(request):
    """
    Сортировка ордеров, чтобы попали свежие ордеры,
    свежие сделки и не разбились группы ордеров.
    - выбрать последние N ордеров
    - выбрать ордеры последних N сделок
    - сложить, взять последние N
    - выбрать все ID групп
    - выбрать ордеры, связанные с этими группами
    """
    account_id = request.GET.get("account", 0)
    symbol = request.GET.get("symbol")
    res = []

    limit = 100

    contract = None
    if symbol:
        try:
            contract = Contract.objects.get(sid=symbol)
        except Contract.DoesNotExist:
            pass

    all_orders = Order.objects.filter(account_id=account_id)
    if symbol:
        all_orders = all_orders.filter(contract=contract)

    last_created = all_orders.order_by("-id")[:limit]

    last_traded = all_orders.filter(trades__order_id__gt=0)
    last_traded = last_traded.order_by("-trades__created_at")[:limit]

    sortable = {}
    ib_by_perm = {}

    oca_groups = set()
    for o in last_created:
        oca_groups.add(o.oca_group)
        ib_by_perm[o.order_id] = o.pk

    for o in last_traded:
        oca_groups.add(o.oca_group)
        ib_by_perm[o.order_id] = o.pk

    oca_groups = list(filter(None, oca_groups))

    # для групповых ордеров вытащить родительский и все соседние ордеры
    group_related = all_orders.filter(
        Q(order_id__in=oca_groups) | Q(oca_group__in=oca_groups)
    )

    for o in group_related:
        ib_by_perm[o.order_id] = o.pk

    # Собрать все ордеры с ключами для сортировки
    for o in list(last_created) + list(last_traded) + list(group_related):
        a = ib_by_perm.get(o.oca_group, 0) if o.oca_group else o.pk
        b = o.pk if o.oca_group else 10**10
        sortable[(a, b)] = o

    sorted_orders = []
    for _, o in sorted(sortable.items(), reverse=True)[:limit]:
        sorted_orders.append(o)

    all_orders_pks = [o.pk for o in sorted_orders]
    related_trades = Trade.objects.filter(order_id__in=all_orders_pks)

    trades_by_order = defaultdict(list)
    for trade in related_trades:
        time = None
        if not time and trade.time:
            time = dt_to_ts(trade.time)
        if not time and trade.created_at:
            time = dt_to_ts(trade.created_at)
        trades_by_order[trade.order_id].append(
            {
                "id": trade.pk,
                "time": time,
                "price": str(trade.price),
                "amount": trade.amount,
            }
        )

    for order in sorted_orders:
        if order.avg_fill_price:
            price = float(order.avg_fill_price)
        elif order.signal_price:
            price = float(order.signal_price)
        else:
            price = ""
        created = None
        time_ts = None
        if order.created_at:
            created = datetime.strftime(order.created_at, "%Y-%m-%d %H:%M:%S")
            time_ts = dt_to_ts(order.created_at)
        sid = order.contract.sid
        name = (sid.split("_", 1)[1]).replace("_", " ")
        res.append(
            {
                "id": order.pk,
                "order_id": order.order_id,
                "local_id": order.local_id,
                "sid": sid,
                "name": name,
                "type": str(order.type).upper(),
                "algo_strategy": order.algo_strategy,
                "oca_group": order.oca_group,
                "amount": order.amount,
                "filled": order.filled,
                "status": order.status,
                "price": price,
                "limit_price": order.limit_price,
                "stop_price": order.stop_price,
                "trailing_amount": order.trailing_amount,
                "trailing_percent": order.trailing_percent,
                "outside_rth": order.outside_rth,
                "side": str(order.action).lower(),
                "time": time_ts,
                "created": created,
                "executions": trades_by_order[order.pk],
            }
        )
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")
