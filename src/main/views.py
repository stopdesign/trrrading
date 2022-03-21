import redis
import orjson
import json
from datetime import timezone, datetime
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from main.models import Account, Instrument, Order


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def backtest(request):
    return render(request, 'backtest_chart.html')


def backtest_data(request):

    f = open("res_URA.ARCA_ChannelBreakout3")
    # f = open("res_URA.ARCA_HullMa")

    data = json.load(f)

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

    if symbol == "indicator":
        for line in data:
            if from_ts < line["ts"] < to_ts:
                res["t"].append(line["ts"])
                res["o"].append(line["up"])
                res["c"].append(line["dn"])
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
                res["v"].append(line["volume"])

    if not len(res["t"]):
        res = {"s": "no_data", "nextTime": 1722108800}

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
        session = "0930-1600"
        instrument_type = "stock"
    data = {
      "name": symbol,
      "exchange-traded": "NasdaqNM",
      "exchange-listed": "NasdaqNM",
      "timezone": "America/New_York",
      "minmovement": 1,
      "minmovement2": 0,
      "pointvalue": 1,
      "session": session,
      "has_intraday": True,
      "has_no_volume": True,
      "description": f"{symbol} Inc.",
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

    r = redis.Redis(
        host=settings.TREDIS_HOST,
        port=settings.TREDIS_PORT,
        db=settings.TREDIS_DB,
        password=settings.TREDIS_PASSWORD,
    )

    symbol = request.GET.get("symbol")

    from_ts = str(request.GET.get("from")).encode()
    to_ts = str(request.GET.get("to")).encode()
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
                rth = 0
                if 14 <= dt.hour < 21 or (13 <= dt.hour < 14 and dt.minute > 30):
                    rth = 1
                ts = dt_to_ts(dt)
                # if rth:
                res["t"].append(ts)
                res["o"].append(j["o"])
                res["h"].append(j["h"])
                res["l"].append(j["l"])
                res["c"].append(j["c"])
                res["v"].append(j["vol"])
                # else:
                #     res["t"].append(ts)
                #     res["o"].append(None)
                #     res["h"].append(None)
                #     res["l"].append(None)
                #     res["c"].append(None)
                #     res["v"].append(None)
                # print(ts, line)
    else:
        res = {"s": "no_data", "nextTime": 1722108800}

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
