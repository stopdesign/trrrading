import glob
import json
import os.path
from datetime import datetime, timedelta, timezone

import orjson
import redis
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render

from main.models import Account, Contract, Order, Position


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

    redis_client = redis.Redis(
        host=settings.TREDIS_HOST,
        port=settings.TREDIS_PORT,
        db=settings.TREDIS_DB,
        password=settings.TREDIS_PASSWORD,
        decode_responses=True,
    )

    try:
        connections = json.loads(str(redis_client.get("connections")))
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
            all_orders = all_orders.prefetch_related().order_by("-id")[:20]
        except Contract.DoesNotExist:
            all_orders = []
    else:
        all_orders = Order.objects.filter(account_id=account_id)
        all_orders = all_orders.prefetch_related().order_by("-id")[:20]
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
        })
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def backtest_data(request):
    symbol = request.GET.get("symbol")

    if symbol.split("#")[0] == "A":
        res = {"s": "no_data", "nextTime": 0}  # данных нет и не будет
        content = json.dumps(res, indent=None, separators=(',', ':'), default=str)
        return HttpResponse(content, content_type="application/json")

    result_id = symbol[:17]
    strategy_id = symbol.split("#")[0][18:]

    base_dir = os.path.abspath(os.path.join(settings.BASE_DIR, "../../res", result_id))
    ohlc_file = f"{base_dir}/{strategy_id}-ohlc.jsonl"

    content = open(ohlc_file).read()

    if content:
        data = orjson.loads("[" + content.strip().replace("\n", ",") + "]")
    else:
        data = []

    res = {
        "t": [],
        "o": [],
        "h": [],
        "l": [],
        "c": [],
        "v": [],
        "s": "ok",
    }

    from_ts = int(request.GET.get("from"))
    to_ts = int(request.GET.get("to"))

    symbol = request.GET.get("symbol")

    if "indicator" in symbol:
        for line in data:
            if from_ts < line["ts"] < to_ts:
                res["t"].append(line["ts"])
                res["o"].append(line.get("up") or line.get("n1"))
                res["c"].append(line.get("dn") or line.get("n2"))
    elif symbol == "profit":
        for line in data:
            if from_ts < line["ts"] < to_ts:
                res["t"].append(line["ts"])
                res["o"].append(line["profit"])
                # res["c"].append(line["dn"])
    else:
        for line in data:
            if from_ts < line["ts"] < to_ts:
                res["t"].append(line["ts"])
                res["o"].append(line["open"])
                res["h"].append(line["high"])
                res["l"].append(line["low"])
                res["c"].append(line["close"])
                res["v"].append(int(line["rth"]))

    # if not len(res["t"]):
    #     res = {"s": "no_data", "nextTime": 1722108800}
    if not len(res["t"]):
        res = {"s": "no_data", "nextTime": from_ts - 3600 * 24 * 3}

    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def config(request):
    data = {
      "supports_search": True,
      "supports_group_request": False,
      "supports_marks": False,
      "supports_timescale_marks": False,
      "supports_time": False,
      "supported_resolutions": ["1", "3", "5", "10", "15", "30"]
    }
    content = json.dumps(data, indent=2, default=str)
    return HttpResponse(content, content_type="application/json")


def symbols(request):
    symbol = request.GET.get("symbol")
    if symbol.count("_") == 2:
        session = "24x7"
        contract_type = "futures"
    else:
        # session = "24x7"
        session = "0930-1600"
        contract_type = "stock"
    data = {
      "name": symbol,
      "exchange-traded": "",
      "exchange-listed": "",
      "timezone": "America/New_York",
      "minmovement": 1,
      "minmovement2": 0,
      "pointvalue": 1,
      "session": session,
      "has_intraday": True,
      "has_no_volume": True,
      "description": f"{symbol}",
      "type": contract_type,
      "supported_resolutions": ["1", "3", "5", "10", "15", "30"],
      "pricescale": 100,
      "ticker": symbol,
    }
    content = json.dumps(data, indent=2, default=str)
    return HttpResponse(content, content_type="application/json")


def time(request):
    cur_time_ts = dt_to_ts(datetime.now())
    return HttpResponse(str(cur_time_ts), content_type="application/json")


def history(request):

    symbol = request.GET.get("symbol")

    if symbol == "A":
        res = {"s": "no_data", "nextTime": 0}  # данных нет и не будет
        content = json.dumps(res, indent=None, separators=(',', ':'), default=str)
        return HttpResponse(content, content_type="application/json")

    r = redis.Redis(
        host=settings.TREDIS_HOST,
        port=settings.TREDIS_PORT,
        db=settings.TREDIS_DB,
        password=settings.TREDIS_PASSWORD,
        decode_responses=True,
    )

    from_ts = int(request.GET.get("from"))
    to_ts = int(request.GET.get("to"))

    # dt = datetime(2022, 12, 6)  #  datetime.utcnow() - timedelta(hours=170)
    # ts = dt_to_ts(dt)
    # # to_ts = ts
    # # print(from_ts, to_ts, ts)
    # from_ts = ts

    data_in_db = r.zrangebyscore(f"{symbol}:TRADES", from_ts, to_ts)

    res = {
        "t": [],
        "o": [],
        "h": [],
        "l": [],
        "c": [],
        "v": [],
        "s": "ok",
    }

    if data_in_db:
        for line in data_in_db:
            j = orjson.loads(line)
            if "o" in j and j["o"] > 0:
                dt = datetime.strptime(j["dt"], "%Y-%m-%d %H:%M:%S")
                # rth = 0
                # if 14 <= dt.hour < 21 or (13 <= dt.hour < 14 and dt.minute > 30):
                #     rth = 1
                ts = dt_to_ts(dt)
                res["t"].append(ts)
                res["o"].append(j["o"])
                res["h"].append(j["h"])
                res["l"].append(j["l"])
                res["c"].append(j["c"])
                res["v"].append(j["v"])

    # TODO: сделать возврат последнего интервала с данными
    if not len(res["t"]):
        res = {"s": "no_data", "nextTime": from_ts - 3600 * 24 * 3}

    content = json.dumps(res, indent=None, separators=(',', ':'), default=str)

    return HttpResponse(content, content_type="application/json")
