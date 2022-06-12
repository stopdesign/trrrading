import glob
import os.path
import redis
import orjson
import json
from datetime import timezone, datetime
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from main.models import Account, Instrument, Order, Position


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


def strategies(request):
    res = []
    result = request.GET.get("result", "")
    base_dir = os.path.abspath(os.path.join(settings.BASE_DIR, "../../res", result))
    files = glob.glob(f"{base_dir}/*_ohlc.jsonl")
    for file in files:
        file = os.path.basename(file)
        instrument, strategy, _ = file.split("_")
        res.append({
            "id": f"{instrument}_{strategy}",
            "strategy": strategy,
            "instrument": instrument,
        })
    res = sorted(res, key=lambda r: (r["instrument"], r["strategy"]))
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def positions(request):
    account_id = request.GET.get("account", 0)
    res = []
    for position in Position.objects.filter(account_id=account_id).prefetch_related():
        res.append({
            "symbol": position.instrument.ticker,
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
    ohlc_file = f"{base_dir}/{strategy_id}_events.jsonl"

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
            "status": "fulled",
            "price": order["price"],
            "profit": order["profit"],
            "side": order["side"],
            "time": order["time"],
            "created": order["dt"],
        })
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def account(request):
    account_id = request.GET.get("account", 0)
    account = Account.objects.get(id=account_id)
    res = {
        "uid": account.uid,
        "net_value": account.net_value,
        "margin_used": account.margin_used,
    }
    content = json.dumps(res, indent=None, default=str)
    return HttpResponse(content, content_type="application/json")


def orders(request):
    account_id = request.GET.get("account", 0)
    symbol = request.GET.get("symbol")
    res = []
    if symbol:
        symbol = symbol.split(".")[0]
        try:
            instrument = Instrument.objects.get(symbol=symbol)
            all_orders = Order.objects.filter(
                account_id=account_id,
                instrument=instrument
            )
            all_orders = all_orders.prefetch_related().order_by("-id")[:20]
        except Instrument.DoesNotExist:
            all_orders = []
    else:
        all_orders = Order.objects.filter(account_id=account_id)
        all_orders = all_orders.prefetch_related().order_by("-id")[:20]
    for order in all_orders:
        if order.avg_fill_price:
            price = float(order.avg_fill_price)
        else:
            price = float(order.signal_price)
        created_at = datetime.strftime(order.created_at, "%Y-%m-%d %H:%M:%S") if order.created_at else None
        res.append({
            "id": order.id,
            "order_id": order.order_id,
            "local_id": order.local_id,
            "symbol": order.instrument.ticker,
            "amount": order.amount,
            "filled": order.filled,
            "status": order.status,
            "price": price,
            "side": order.action.lower(),
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
    ohlc_file = f"{base_dir}/{strategy_id}_ohlc.jsonl"

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
      "supported_resolutions": ["1", "5", "15", "30", "1H", "2H", "3H", "4H", "1D", "1W"],
    }
    content = json.dumps(data, indent=2, default=str)
    return HttpResponse(content, content_type="application/json")


def symbols(request):
    symbol = request.GET.get("symbol")
    if "GLOBEX" in symbol:
        session = "24x7"
        instrument_type = "futures"
    else:
        # session = "24x7"
        session = "0930-1600"
        instrument_type = "stock"
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
      "type": instrument_type,
      "supported_resolutions": ["1", "5", "15", "30", "1H", "2H", "3H", "4H", "1D", "1W"],
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
    )

    from_ts = int(request.GET.get("from"))
    to_ts = int(request.GET.get("to"))

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
            j = orjson.loads(line.decode('utf-8'))
            if "o" in j:
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
                res["v"].append(j["vol"])

    # TODO: сделать возврат последнего интервала с данными
    if not len(res["t"]):
        res = {"s": "no_data", "nextTime": from_ts - 3600 * 24 * 3}

    content = json.dumps(res, indent=None, separators=(',', ':'), default=str)

    return HttpResponse(content, content_type="application/json")


def marks(request):

    account = Account.objects.get(id=1)
    instrument = Instrument.objects.get(symbol="MES")

    orders = Order.objects.filter(account=account, instrument=instrument)

    times = [1647364100]
    ids = [123]
    labels = ["sdfa"]
    prices = [24]
    colors = ["red"]
    texts = ["asdfas"]

    # for order in orders:
    #     times.append(dt_to_ts(order.created_at))
    #     ids.append(len(ids))
    #     labels.append(order.action)
    #     prices.append(order.avg_fill_price)
    #     colors.append("red" if order.action == "SELL" else "green")
    #     texts.append(order.created_at.strftime('%H:%M:%S') + " @" + str(order.avg_fill_price))

    # 1639304000
    data = {
        "id": ids,
        "time": times,
        "color": colors,
        "text": texts,
        "label": labels,
        "minSize": 10,
        "price": prices,
    }
    content = json.dumps(data, indent=2, default=str)
    return HttpResponse(content, content_type="application/json")


def timescale_marks(request):
    data = [
        {"id": "tsm1", "time": 1522108800, "color": "red", "label": "A", "tooltip": ""},
        {
            "id": "tsm2",
            "time": 1521763200,
            "color": "blue",
            "label": "D",
            "tooltip": ["Dividends: $0.56", "Date: Fri Mar 23 2018"],
        },
        {
            "id": "tsm3",
            "time": 1521504000,
            "color": "green",
            "label": "D",
            "tooltip": ["Dividends: $3.46", "Date: Tue Mar 20 2018"],
        },
        {
            "id": "tsm4",
            "time": 1520812800,
            "color": "#999999",
            "label": "E",
            "tooltip": ["Earnings: $3.44", "Estimate: $3.60"],
        },
        {
            "id": "tsm7",
            "time": 1519516800,
            "color": "red",
            "label": "E",
            "tooltip": ["Earnings: $5.40", "Estimate: $5.00"],
        },
    ]
    content = json.dumps(data, indent=2, default=str)
    return HttpResponse(content, content_type="application/json")
