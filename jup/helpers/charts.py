import plotly.graph_objects as go


def get_price_trace(df):
    increasing = go.candlestick.Increasing(
        line=dict(width=1, color="#8bb"),
        fillcolor="#8bb",
    )
    decreasing = go.candlestick.Decreasing(
        line=dict(width=1, color="#eaa"),
        fillcolor="#eaa",
    )
    ohlc = go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing=increasing,
        decreasing=decreasing,
        showlegend=False,
    )
    return ohlc


def get_layout(yrange=None, width=800, height=800):
    xaxis = {
        "showgrid": True,
        "gridcolor": "#eee",
        "gridwidth": 1,
        "rangeslider_visible": False,
    }
    yaxis = {
        "showgrid": True,
        "gridcolor": "#eee",
        "gridwidth": 1,
        "range": yrange,
        # "fixedrange": True,
    }
    layout = go.Layout(
        width=width,
        height=height,
        autosize=False,
        margin=dict(t=20, b=20, l=0, r=0),
        xaxis=xaxis,
        yaxis=yaxis,
        font=dict(family="Menlo, monospace", size=11, color="#444"),
        template="simple_white",
        showlegend=False,
    )
    return layout


def get_trace(fig, df, symbol="x"):
    x = df.index
    if df.price_close.any():
        y = df.price_close
    else:
        y = df.price
    if y is None:
        return
    color = "#90f"
    line_width = 1.6
    if "bar" in symbol:
        color = "#000"
    elif "up" in symbol:
        color = "#e00"
    elif "down" in symbol:
        color = "#090"
    else:
        line_width = 0
    trace = go.Scatter(
        x=x,
        y=y,
        mode="markers",
        marker=dict(
            symbol=symbol,
            size=7,
            color="#fff",
            line_color="#fff",
            line_width=line_width + 3,
        ),
        showlegend=False,
    )
    fig.add_trace(trace)
    trace = go.Scatter(
        x=x,
        y=y,
        mode="markers",
        marker=dict(
            symbol=symbol,
            size=7,
            color=color,
            line_color=color,
            line_width=line_width,
        ),
        showlegend=False,
    )
    fig.add_trace(trace)


def add_trade_markers(fig, md):
    """
    Маркеры сделок
    """
    get_trace(fig, md[md.action == "enter_long"], "arrow-up")
    get_trace(fig, md[md.action == "enter_short"], "arrow-down")
    get_trace(fig, md[md.action == "exit_long"], "arrow-bar-down")
    get_trace(fig, md[md.action == "exit_short"], "arrow-bar-up")
    get_trace(fig, md[md.action == "stop_long"], "x")
    get_trace(fig, md[md.action == "stop_short"], "x")


def detect_range_rule(md):
    len_minutes = (md.index[1] - md.index[0]).total_seconds()
    len_minutes = int(len_minutes / 60)
    day_int = int(len_minutes / (60 * 24))
    day_remainder = len_minutes % (60 * 24)
    hour_int = int(len_minutes / 60)
    hour_remainder = len_minutes % 60
    if day_int > 0 and day_remainder == 0:
        rule = f"{day_int}d"
    elif hour_int > 0 and hour_remainder == 0:
        rule = f"{hour_int}h"
    else:
        rule = f"{len_minutes}T"
    return len_minutes, rule


def remove_x_gaps(fig, md, df=None, skip_start=20, skip_end=None):
    """
    Убрать дыры в оси X
    """
    if df is None:
        df = md

    index_start = df.index[skip_start or 0]
    index_end = df.index[-1 - (skip_end or 0)]

    len_minutes, rule = detect_range_rule(md)

    close_na = df["close"].asfreq(rule).isna()
    gaps = close_na[close_na.values].index
    data_rangebreaks = {
        "values": list(gaps),
        "dvalue": len_minutes * 60 * 1000,
    }
    fig.update_xaxes(
        range=[index_start, index_end],
        rangebreaks=[data_rangebreaks],
    )


# Оформление индикатора
# fig.add_hline(y=0, line=dict(color="#000", width=1), row=2)
# fig.add_hline(y=0.3, line=dict(color="blue", width=1), row=2)
# fig.add_hline(y=-0.3, line=dict(color="red", width=1), row=2)
# fig.add_hrect(y0=0, y1=20, line_width=0, fillcolor="green", opacity=0.1, row=2)
# fig.add_hrect(y0=0, y1=-20, line_width=0, fillcolor="red", opacity=0.1, row=2)


# from plotly import offline
# fig.layout.width = 2000
# fig.layout.height = 1000
# offline.plot(fig, filename="filename.html", auto_open=True)
