import glob
import json
import os.path
from collections import defaultdict
from datetime import datetime, timezone

import orjson
import requests
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render

from main.models import Account, Contract, Order, Position, Trade


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def dashboard(request):
    try:
        account_id = Account.objects.latest('updated_at').id
    except Order.DoesNotExist:
        account_id = 0
    return render(request, 'react_dashboard.html', {"account_id": account_id})


def backtest(request):
    base_dir = os.path.abspath(os.path.join(settings.BASE_DIR, "../../res"))
    results = list(sorted(next(os.walk(base_dir))[1], reverse=True))[:5]
    context = {
        "backtest_results": results,
    }
    return render(request, 'backtest_chart.html', context)


def bt_raw(request):

    symbol = request.GET.get("symbol")
    result_id = symbol[:17]
    strategy_id = symbol.split("#")[0][18:]

    print(strategy_id)

    base_dir = os.path.abspath(os.path.join(settings.BASE_DIR, "../../res", result_id))
    ohlc_file = f"{base_dir}/{strategy_id}-ohlc.jsonl"

    content = "[" + open(ohlc_file).read().replace("\n", ",\n").strip(",\n") + "]"

    return HttpResponse(content, content_type="application/json")


def results(request):
    base_dir = os.path.abspath(os.path.join(settings.BASE_DIR, "../../res"))
    results = list(sorted(next(os.walk(base_dir))[1], reverse=True))[:20]
    # res = sorted(res, key=lambda r: (r["contract"], r["strategy"]))
    res = {
        "results": sorted(results, reverse=True),
    }
    context = json.dumps(res, indent=None, default=str)
    return HttpResponse(context, content_type="application/json")


def strategies(request):
    res = []
    result = request.GET.get("result", "")
    base_dir = os.path.abspath(os.path.join(settings.BASE_DIR, "../../res", result))
    files = glob.glob(f"{base_dir}/*-ohlc.jsonl")
    for file in files:
        file = os.path.basename(file)
        instrument, strategy, data_type = file.split("-")
        res.append({
            "id": f"{instrument}-{strategy}",
            "strategy": strategy,
            "instrument": instrument,
        })
    res = sorted(res, key=lambda r: (r["instrument"], r["strategy"]))
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def positions(request):
    account_id = request.GET.get("account", 0)
    res = []
    positions = Position.objects.filter(account_id=account_id).prefetch_related()
    positions = positions.order_by("-avg_price")
    for position in positions:
        res.append({
            "symbol": position.contract.sid,
            "amount": position.amount,
            "avg_price": position.avg_price,
            "unrealized_pnl": position.unrealized_pnl,
            "updated": position.updated_at,
        })
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def bt_events(request):
    # ?result=2022-04-13_078181&strategy=COPX.ARCA_ChannelBreakout3
    result_id = request.GET.get("result")
    strategy_id = request.GET.get("strategy")

    base_dir = os.path.abspath(os.path.join(settings.BASE_DIR, "../../res", result_id))
    ohlc_file = f"{base_dir}/{strategy_id}-events.jsonl"

    content = open(ohlc_file).read()

    if content:
        data = orjson.loads("[" + content.strip().replace("\n", ",") + "]")
    else:
        data = []

    res = []

    for i, order in enumerate(data):
        res.append({
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
        })
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
    }
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def orders(request):
    account_id = request.GET.get("account", 0)
    symbol = request.GET.get("symbol")
    res = []
    if symbol:
        try:
            contract = Contract.objects.get(sid=symbol)
            all_orders = Order.objects.filter(
                account_id=account_id,
                contract=contract
            )
            all_orders = all_orders.order_by("-id")[:20]
        except Contract.DoesNotExist:
            all_orders = []
    else:
        all_orders = Order.objects.filter(account_id=account_id)
        all_orders = all_orders.order_by("-id")[:20]

    all_orders_pks = [o.pk for o in all_orders]
    related_trades = Trade.objects.filter(order_id__in=all_orders_pks)

    trades_by_order = defaultdict(list)
    for trade in related_trades:
        time = None
        if not time and trade.time:
            time = dt_to_ts(trade.time)
        if not time and trade.created_at:
            time = dt_to_ts(trade.created_at)
        trades_by_order[trade.order_id].append({
            "id": trade.pk,
            "time": time,
            "price": str(trade.price),
            "amount": trade.amount,
        })

    for order in all_orders:
        if order.avg_fill_price:
            price = float(order.avg_fill_price)
        elif order.signal_price:
            price = float(order.signal_price)
        else:
            price = "-"
        created_at = datetime.strftime(order.created_at, "%Y-%m-%d %H:%M:%S") if order.created_at else None
        res.append({
            "id": order.pk,
            "order_id": order.order_id,
            "local_id": order.local_id,
            "sid": order.contract.sid,
            "type": order.type,
            "amount": order.amount,
            "filled": order.filled,
            "status": order.status,
            "price": price,
            "limit_price": order.limit_price,
            "stop_price": order.stop_price,
            "side": str(order.action).lower(),
            "time": dt_to_ts(order.created_at) if order.created_at else None,
            "created": created_at,
            "executions": trades_by_order[order.pk],
        })
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")
