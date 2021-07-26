import json  # noqa
import sys
import math
import scipy.stats
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal
from termcolor import cprint, colored
from advisor import Advisor
from exchange import BacktestExchange, ExanteExchange, InteractiveBrokersExchange  # noqa
from notifications.alert import send_telegram  # noqa
from strategy import Signal
from util import interval_dt, unix_timestamp
from settings import CAN_SHORT


CURSOR_UP_ONE = "\x1b[1A"
ERASE_LINE = "\x1b[2K"


# def cprint(*args, **kwargs):
#     pass


class Trader:

    def __init__(self, advisors=None, dt_start=None):
        cprint("Init trader", "white")

        self.can_short = CAN_SHORT
        self.reinvest_profit = False

        self.dt_start = dt_start or datetime(2021, 3, 1)
        self.dt_chart_start = self.dt_start  # + timedelta(days=2)

        self.advisors = advisors

        self.log_intervals = "Date,Open,High,Low,Close\n"
        self.log_trades = "Date,Direction,Price,Profit\n"
        self.log_stats = "Date,Value,Drawdown,Equity,RelEquity\n"

        ss = list(set([a.instrument for a in self.advisors]))

        dt_from = self.dt_start - timedelta(days=50)
        self.exchange = BacktestExchange(
            ss, dt_start=self.dt_start, dt_from=dt_from, mode="60"
        )
        # self.exchange = ExanteExchange(ss)
        # self.exchange = InteractiveBrokersExchange(ss, loop=loop)

        cprint("Historical data", "white")

        # Прогнать события по историческим данным.
        # Предзаполняются цены и сигналы, торговля не происходит.
        self.exchange.process_historical_data(self.on_event)

        # Нужно получить достаточно данных, чтобы стратегия смогла
        # восстановить последний торговый сигнал.
        invalid_advisor = False
        for advisor in self.get_advisors():
            if advisor.state not in [Signal.LONG, Signal.SHORT, Signal.CLOSE]:
                invalid_advisor = True
                cprint(f" NO STATE: {advisor} ", color="red", attrs=["reverse"])
        if invalid_advisor:
            raise Exception("no state")
            # sys.exit(1)

        self.portfolio_info()

        self.max_net_value = Decimal("-Infinity")
        self.max_drawdown = Decimal("-Infinity")
        self.cur_drawdown = 0
        self.gross_profit = 0
        self.gross_loss = 0
        self.trades_count = {"buy": 0, "sell": 0, "close": 0}
        self.prev_net_value = self.exchange.net_value

        self.deposits = [self.exchange.cash_initial]

        log = f"{self.exchange.net_value:0.2f},{self.cur_drawdown:0.2f},0,0\n"
        self.log_stats += f"{self.dt_start},{log}"

    def start(self, loop=None):
        cprint("Start listening for updates...", "white")
        self.exchange.start_listen(self.on_event, loop)

    def stop(self, loop=None):  # noqa
        # Актуализация статистики DD
        drawdown = max(Decimal(0), self.max_net_value - self.exchange.net_value)
        self.max_net_value = max(self.max_net_value, self.exchange.net_value)
        self.cur_drawdown = drawdown / self.max_net_value * 100
        self.max_drawdown = max(self.max_drawdown, self.cur_drawdown)

        self.exchange.stop_listen()

        # Подсчет gross profit/loss после закрытия
        self.update_profit_loss()

    def update_profit_loss(self):
        diff_value = self.exchange.net_value - self.prev_net_value
        self.gross_profit += max(0, diff_value)
        self.gross_loss += min(0, diff_value)
        self.prev_net_value = self.exchange.net_value
        self.deposits.append(self.exchange.net_value)
        return diff_value

    def final_info(self):
        cprint("\n" + colored(" RESULTS ", attrs=["reverse"]))
        self.portfolio_info()
        pf = self.gross_profit / abs(self.gross_loss) if self.gross_loss else 0
        p = self.exchange.net_value - self.exchange.cash_initial
        roi = p / self.exchange.cash_initial * 100
        trades = self.trades_count["buy"] + self.trades_count["sell"]

        # R2
        x = np.arange(len(self.deposits))
        y = np.array(self.deposits, dtype=float)
        slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(x, y)
        r2 = r_value ** 2

        txt = (
            "\n"
            f"ROI: {roi:+7.1f}%\n"
            f"Max DD: {self.max_drawdown:4.1f}%\n"
            f"PF: {pf:9.2f}\n"
            f"R²: {r2:9.2f}\n"
            f"Trades: {trades:5.0f}\n"
            f"GP: {self.gross_profit:+9.0f}\n"
            f"GL: {self.gross_loss:+9.0f}"
        )
        cprint(txt)

        with open("trades.csv", "w") as t:
            t.write(self.log_trades)

        # Исторические данные собираются из специальных Dummy strategy
        last_known_dt = self.dt_start
        for advisor in self.get_advisors(include_dummy=True):
            if hasattr(advisor.strategy, "final_info"):
                advisor.strategy.final_info()

            if advisor.strategy.__class__.__name__ != "Dummy":
                continue

            for interval in advisor.strategy.historical:
                last_known_dt = interval_dt(interval)
                if last_known_dt < self.dt_chart_start:
                    continue
                if self.advisors[0].is_main_session(last_known_dt):
                    log = "{open},{high},{low},{close}\n".format(**interval)
                    self.log_intervals += f"{last_known_dt},{log}"

        log_indicators = "Date,"
        for advisor in self.get_advisors():
            if hasattr(advisor.strategy, "indicator_data"):
                keys = advisor.strategy.indicator_data[0].keys()
                log_indicators += ",".join(keys) + "\n"
                for row in advisor.strategy.indicator_data:
                    ts = row["timestamp"]
                    val = ""
                    for v in row.values():
                        val += f",{v}"
                    log_indicators += f"{ts}{val}\n"
                break

        with open("indicator.csv", "w") as d:
            d.write(log_indicators)

        with open("data.csv", "w") as d:
            d.write(self.log_intervals)

        log = f"{self.exchange.net_value:0.2f},{self.cur_drawdown:0.2f}\n"
        self.log_stats += f"{last_known_dt},{log}"

        with open("stats.csv", "w") as s:
            s.write(self.log_stats)

    def on_event(self, event_type, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        # if "historical" not in event_type and event_type != "quote":
        #     cprint(f"{dt}: EVENT {event_type} {symbol}", "white")

        # На бирже произошла новая сделка
        if event_type == "trade":
            self.on_trade(dt, symbol, payload["price"], payload["size"])

        # Это должно происходить после запуска on_trade  TODO: СХУЯЛИ?
        if event_type in ["trade", "historical_trade"]:
            # Добавление нового значения цены в стратегию
            for advisor in self.get_advisors(symbol, include_dummy=True):
                ts = unix_timestamp(dt, micro=True)
                price = payload["price"]
                advisor.update_strategy(dt, {"timestamp": ts, "price": price})

        if event_type in ["quote", "historical_quote"]:
            self.exchange.add_quote(dt, symbol, payload)

        if event_type == "before_interval":
            # Логи: статистика на начало интервала
            # if self.advisors[0].is_main_session(dt):

            net = self.exchange.net_value
            eq = self.exchange.equity_value
            rel_eq = self.exchange.equity_value / net * 100

            sys.stdout.write(CURSOR_UP_ONE)
            sys.stdout.write(ERASE_LINE)
            txt = (  # noqa
                f"{dt}: "
                f"net: {net:0.0f}  "
                f"rel_eq: {rel_eq:0.0f}  "
                f"dd: {self.cur_drawdown:0.1f}%  "
                f"max dd: {self.max_drawdown:0.1f}%  "
            )
            # cprint(txt, "white")

            log = f"{net:0.2f},{self.cur_drawdown:0.2f},{eq:0.2f},{rel_eq:0.2f}\n"
            self.log_stats += f"{dt},{log}"

        # After any exchange event
        if event_type in ["trade", "quote"]:
            # Обновление статистики
            net = self.exchange.net_value
            if self.advisors[0].is_main_session(dt):
                drawdown = max(Decimal(0), self.max_net_value - net)
                self.max_net_value = max(self.max_net_value, net)
                self.cur_drawdown = drawdown / self.max_net_value * 100
                self.max_drawdown = max(self.max_drawdown, self.cur_drawdown)

        return True

    def get_advisors(self, instrument=None, include_dummy=False):
        """
        Все советники для данного инструмента.
        """
        res = []
        for advisor in self.advisors:
            if not include_dummy and advisor.strategy.__class__.__name__ == "Dummy":
                continue
            if not instrument or advisor.instrument == instrument:
                res.append(advisor)
        return res

    def get_current_position(self, instrument):
        """
        Сколько сейчас в портфолио этой штуки.
        """
        positions = self.exchange.get_positions()
        return positions.get(instrument, BacktestExchange.empty_position)["amount"]

    def get_advised_position(self, instrument):
        """
        Сколько сейчас в портфолио должно быть этой штуки,
        если бы сработали все исторические сигналы.
        """
        buying_power = self.get_buying_power()

        res = Decimal("0")
        for advisor in self.get_advisors(instrument):
            if advisor.state == Signal.LONG:
                price = self.exchange.get_price(instrument, "buy")
                amount = math.floor(buying_power / price)
                res += amount
            if advisor.state == Signal.SHORT:
                price = self.exchange.get_price(instrument, "sell")
                amount = math.floor(buying_power / price)
                res -= amount
            if advisor.state == Signal.CLOSE:
                res = Decimal(0)

        # Если нельзя шортить
        if not self.can_short:
            res = max(Decimal(0), res)

        return res

    def get_buying_power(self):
        """
        Сумма, которой может управлять один советник.

        Сейчас депозит делится равными долями между всеми.
        Если reinvest_profit выключен, то делится начальный депозит.
        """
        if self.reinvest_profit:
            cash_to_use = self.exchange.net_value
        else:
            cash_to_use = min(self.exchange.cash_initial, self.exchange.net_value)
        cnt = len(self.get_advisors())
        if cnt:
            return cash_to_use / cnt
        else:
            return Decimal(0)

    def portfolio_info(self):
        """
        Вывод информации о состоянии портфолио.
        """
        cprint("")
        for instrument in sorted(set([a.instrument for a in self.get_advisors()])):
            current_position = self.get_current_position(instrument)
            advised_position = self.get_advised_position(instrument)
            cprint(
                f"{instrument:<12} "
                f"current: {current_position:+6.0f},   "
                f"advised: {advised_position:+6.0f}  ",
                "blue",
            )
        cprint(
            f"CASH: {self.exchange.cash:0.0f},  "
            f"VALUE: {self.exchange.net_value:0.0f},  "
            f"EQUITY: {self.exchange.equity_value:0.0f}",
            "green",
        )
        cprint("")

    def on_trade(self, dt: datetime, instrument, trade_price, volume=None):  # noqa
        """
        Тут торговля, если стратегия дала сигнал.
        Здесь же риск-менеджмент уровня аккаунта,
        контроль использования маржи.
        """
        # cprint(f"\nON_TRADE {dt} {instrument} {trade_price}", "cyan")
        # self.portfolio_info()

        # Протестировать новую цену (не добавляя в историю).
        # Получить суммарный объем на покупку/продажу по всем сигналам.
        total_buy, total_sell = self.test_new_price(instrument, dt, trade_price)

        # Это всё должно быть после тестирования новой цены // TODO: почему?
        current_position = self.get_current_position(instrument)
        advised_position = self.get_advised_position(instrument)

        diff = advised_position - current_position

        # Всё равно ничего сделать нельзя
        if not (diff and (total_buy or total_sell)):
            # cprint(f"SKIP: diff: {diff}, buy: {total_buy}, sell: {total_sell}")
            return

        # Посчитать, куда нужно торговать.
        # Скоректировать объем по возможностям, которые есть по сигналам.
        side = None
        asset_amount_diff = 0
        if diff > 0:
            asset_amount_diff = min(abs(diff), total_buy)
            side = "buy"
        elif diff < 0:
            asset_amount_diff = min(abs(diff), total_sell)
            side = "sell"

        price = self.exchange.get_price(instrument, side)
        min_tradable_amount = self.get_min_tradable_amount(price)

        # Предлагаемое изменение должно быть больше минимального
        if asset_amount_diff < min_tradable_amount:
            asset_amount_diff = 0
            side = None

        # Логи: какая операция должна произойти
        symbol_str = colored(f"{instrument:>10}", attrs=["bold"])
        color = "cyan"
        sign = "*** "
        if side == "buy":
            color = "green"
            sign = "+"
        if side == "sell":
            color = "red"
            sign = "-"
        action = colored(f"{(sign+str(asset_amount_diff)):>5}", color)

        price_diff = abs(trade_price - price) / price * 100
        txt = (
            f"{dt:%Y-%m-%d %H:%M:%S}  {symbol_str}    "
            f"cur/adv: {current_position:+6.0f} {advised_position:+6.0f}    "
            f"signal: {total_buy:+5.0f} {-total_sell:+5.0f}    "
            f"do: {action}    𝝙: {price_diff:0.2f}"
        )
        txt = txt.replace("+0", colored(" 0", "white"))
        cprint(txt)
        # send_telegram(txt)

        # Если есть все параметры — запустить сделку
        if price and side and asset_amount_diff:
            self.trades_count[side] += 1

            assert self.prev_net_value is not None

            # Сделка
            self.exchange.trade(side, asset_amount_diff, instrument)

            # Подсчет gross profit/loss после каждой сделки
            profit_loss = self.update_profit_loss()

            txt = f"{dt:%Y-%m-%d %H:%M:%S},{side},{price:0.4f},{profit_loss:0.4f}\n"
            self.log_trades += txt
            # cprint(txt)

            # Записать log_stats сразу после сделки.
            # Не уверен, что это нужно.
            self.on_event("before_interval", dt, instrument)

    def get_min_tradable_amount(self, price):
        """
        Минимальное количество акций, которое стоит покупать/продавать.
        """
        symbols = list(set([a.instrument for a in self.get_advisors()]))
        cash_per_symbol = self.exchange.net_value / len(symbols)
        min_tradable_amount = math.floor((cash_per_symbol / 10) / price)
        min_tradable_amount = max(1, min_tradable_amount)
        return min_tradable_amount

    def test_new_price(self, instrument, dt, price):
        """
        Посчитать суммарный объем покупки и продажи,
        который предлагают советники для новой цены
        """
        # Сумма, которой может управлять один советник
        buying_power = self.get_buying_power()

        total_buy, total_sell = Decimal("0"), Decimal("0")

        for advisor in self.get_advisors(instrument):
            current_state = advisor.state
            signal = advisor.test_price(dt, price)
            if signal == Signal.LONG:
                cur_price = self.exchange.get_price(instrument, "buy")
                amount = math.floor(buying_power / cur_price)
                if current_state == Signal.SHORT:
                    total_buy += amount * 2
                elif current_state == Signal.LONG:
                    total_buy += 0
                else:
                    total_buy += amount
            if signal == Signal.SHORT:
                cur_price = self.exchange.get_price(instrument, "sell")
                amount = math.floor(buying_power / cur_price)
                if current_state == Signal.LONG:
                    total_sell += amount * 2
                elif current_state == Signal.SHORT:
                    total_sell += 0
                else:
                    total_sell += amount
            if signal == Signal.CLOSE:
                if current_state == Signal.LONG:
                    cur_price = self.exchange.get_price(instrument, "sell")
                    amount = math.floor(buying_power / cur_price)
                    total_sell += amount
                elif current_state == Signal.SHORT:
                    cur_price = self.exchange.get_price(instrument, "buy")
                    amount = math.floor(buying_power / cur_price)
                    total_buy += amount

        return total_buy, total_sell
