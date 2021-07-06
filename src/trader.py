import sys
import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from termcolor import cprint, colored
from advisor import Advisor
from exchange import BacktestExchange, ExanteExchange
from notifications.alert import send_telegram
from strategy import Signal
from util import interval_dt, reformat_ohlc, load_from_file
from settings import CAN_SHORT


CURSOR_UP_ONE = "\x1b[1A"
ERASE_LINE = "\x1b[2K"


class Trader:
    def __init__(self):
        cprint("Init trader", "white")

        self.log_intervals = "Date,Open,High,Low,Close\n"
        self.log_trades = "Date,Direction,Price,Profit\n"
        self.log_stats = "Date,Value,Drawdown,Equity,RelEquity\n"

        self.can_short = CAN_SHORT

        self.dt_start = datetime(2021, 1, 1).astimezone(timezone.utc)
        dt_from = self.dt_start - timedelta(days=4)
        self.dt_chart_start = self.dt_start + timedelta(days=6)

        # Как торговать
        self.advisors = [
            # Advisor("Dummy", "USD/CAD.E.FX", interval=3*60*60, extra_hours=True, extra_hours_data=True),

            # До 2021 показывает пиздец
            # Advisor(strategy="Volty", length=500, instrument="COPX.ARCA", extra_hours_data=False),  # p:177% dd:10%
            # Advisor(strategy="Volty", length=500, instrument="COPX.ARCA", extra_hours_data=False),  # p:177% dd:10%

            # До 2021 показывает пиздец
            # Advisor(strategy="ParabolicSAR", length=100, interval=3600, instrument="COPX.ARCA", extra_hours_data=False),  # p:211% dd:8.8%
            Advisor(strategy="ParabolicSAR", length=100, interval=3600, instrument="COPX.ARCA", extra_hours_data=False),  # p:211% dd:8.8%
            Advisor(strategy="ParabolicSAR", length=100, interval=7200, instrument="COPX.ARCA", extra_hours_data=False),  # p:180% dd:12%

            # Advisor(strategy="ChannelBreakout", length=350, instrument="COPX.ARCA"),
            # Advisor(strategy="ChannelBreakout", length=450, instrument="COPX.ARCA"),
            # Advisor(strategy="ChannelBreakout", length=550, instrument="COPX.ARCA"),
            #
            # Advisor(strategy="ChannelBreakout", length=450, instrument="URA.ARCA"),
            # Advisor(strategy="ChannelBreakout", length=520, instrument="URA.ARCA"),
            # Advisor(strategy="ChannelBreakout", length=600, instrument="URA.ARCA"),
        ]

        symbols = list(set([a.instrument for a in self.advisors]))

        self.exchange = BacktestExchange(symbols, dt_start=self.dt_start, dt_from=dt_from)
        # self.exchange = ExanteExchange(symbols)

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
            sys.exit(1)

        print()
        self.portfolio_info()
        print()

        self.max_net_value = Decimal("-Infinity")
        self.max_drawdown = Decimal("-Infinity")
        self.cur_drawdown = 0
        self.gross_profit = 0
        self.gross_loss = 0
        self.trades_count = {"buy": 0, "sell": 0, "close": 0}
        self.prev_net_value = self.exchange.net_value

        log = f"{self.exchange.net_value:0.2f},{self.cur_drawdown:0.2f}\n"
        self.log_stats += f"{self.dt_start:%Y-%m-%d %H:%M:%S},{log}"

    def start(self, loop):
        cprint("Start listening for updates...", "white")
        self.exchange.start_listen(self.on_event, loop)

    def stop(self, loop=None):  # noqa
        self.exchange.stop_listen()

        # Актуализация статистики DD
        drawdown = max(Decimal(0), self.max_net_value - self.exchange.net_value)
        self.max_net_value = max(self.max_net_value, self.exchange.net_value)
        self.cur_drawdown = drawdown / self.max_net_value * 100
        self.max_drawdown = max(self.max_drawdown, self.cur_drawdown)

        # Подсчет gross profit/loss после закрытия
        diff_value = self.exchange.net_value - self.prev_net_value
        self.gross_profit += max(0, diff_value)
        self.gross_loss += min(0, diff_value)
        self.prev_net_value = self.exchange.net_value

    def final_info(self):
        print()
        cprint(" Result ", attrs=["reverse"])
        self.portfolio_info()
        print()
        pf = self.gross_profit / abs(self.gross_loss) if self.gross_loss else 0
        cprint(
            f"net: {self.exchange.net_value:0.0f}  "
            f"cur dd: {self.cur_drawdown:0.1f}%  "
            f"max dd: {self.max_drawdown:0.1f}%  "
            f"gp: {self.gross_profit:+0.0f}  "
            f"gl: {self.gross_loss:+0.0f}  "
            f"pf: {pf:0.2f}  "
        )

        with open("trades.csv", "w") as t:
            t.write(self.log_trades)

        # Исторические данные собираются из специальных Dummy strategy
        last_known_dt = self.dt_start
        for advisor in self.get_advisors():
            if hasattr(advisor.strategy, "final_info"):
                advisor.strategy.final_info()

            # TODO: historical не должны забираться из advisor
            data = advisor.strategy.historical
            data = reformat_ohlc(data, 3600)

            for interval in data:
                dt = interval_dt(interval)
                log = "{open},{high},{low},{close}\n".format(**interval)
                self.log_intervals += f"{dt:%Y-%m-%d %H:%M:%S},{log}"

        log_indicators = "Date,"
        for advisor in self.get_advisors():
            if hasattr(advisor.strategy, "indicator_data"):
                log_indicators += ",".join(advisor.strategy.indicator_data[0].keys()) + "\n"
                for row in advisor.strategy.indicator_data:
                    ts = row["timestamp"]
                    val = ""
                    for v in row.values():
                        val += f",{v}"
                    log_indicators += f"{ts:%Y-%m-%d %H:%M:%S}{val}\n"
                break

        with open("indicator.csv", "w") as d:
            d.write(log_indicators)

        # # Прямой проброс входных OHLC в log_intervals
        # trades_file = f"../data/forex/live-EUR:CHF.E.FX-quotes-60-small.jsonl"
        # trades_ohlc = load_from_file(trades_file, self.dt_start, "EUR:CHF.E.FX")
        # trades_ohlc = reformat_ohlc(trades_ohlc, 300)
        # for interval in trades_ohlc:
        #     dt = interval_dt(interval)
        #     if dt > self.dt_start:
        #         log = "{open},{high},{low},{close}\n".format(**interval)
        #         self.log_intervals += f"{dt:%Y-%m-%d %H:%M:%S},{log}"

        with open("data.csv", "w") as d:
            d.write(self.log_intervals)

        log = f"{self.exchange.net_value:0.2f},{self.cur_drawdown:0.2f}\n"
        self.log_stats += f"{last_known_dt:%Y-%m-%d %H:%M:%S},{log}"

        with open("stats.csv", "w") as s:
            s.write(self.log_stats)

    def on_event(self, event_type, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        # cprint(f"{dt:%Y-%m-%d %H:%M:%S}: EVENT {event_type} {symbol}", "white")

        if event_type == "trade":
            self.on_trade(dt, symbol, payload["price"], payload["size"])

        # Это должно происходить после запуска on_trade
        if event_type in ["trade", "historical_trade"]:
            # Добавление нового значения цены в стратегию
            for advisor in self.get_advisors(symbol):
                ts = dt.timestamp() * 1000
                advisor.update_strategy({"timestamp": ts, "price": payload["price"]})

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
            txt = (
                f"{dt:%Y-%m-%d %H:%M:%S}: "
                f"net: {net:0.0f}  "
                f"rel_eq: {rel_eq:0.0f}  "
                f"dd: {self.cur_drawdown:0.1f}%  "
                f"max dd: {self.max_drawdown:0.1f}%  "
            )
            cprint(txt, "white")

            log = f"{net:0.1f},{self.cur_drawdown:0.1f},{eq:0.1f},{rel_eq:0.1f}\n"
            self.log_stats += f"{dt:%Y-%m-%d %H:%M:%S},{log}"

        # After any exchange event
        if event_type in ["trade", "quote"]:
            # Обновление статистики
            net_value = self.exchange.net_value
            if self.advisors[0].is_main_session(dt):
                drawdown = max(Decimal(0), self.max_net_value - net_value)
                self.max_net_value = max(self.max_net_value, net_value)
                self.cur_drawdown = drawdown / self.max_net_value * 100
                self.max_drawdown = max(self.max_drawdown, self.cur_drawdown)

        return True

    def get_advisors(self, instrument=None):
        """
        Все советники для данного инструмента.
        """
        if not instrument:
            return self.advisors
        return [a for a in self.advisors if a.instrument == instrument]

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
        res = Decimal("0")
        cash_to_use = min(self.exchange.cash_initial, self.exchange.net_value)
        buying_power = cash_to_use / len(self.advisors)
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

    def portfolio_info(self):
        """
        Вывод информации о состоянии портфолио.
        """
        for instrument in sorted(set([a.instrument for a in self.advisors])):
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
            f"VALUE: {self.exchange.net_value:0.0f}",
            "green",
        )

    def on_trade(self, dt: datetime, instrument, price, volume=None):  # noqa
        """
        Тут торговля, если стратегия дала сигнал.
        Здесь же риск-менеджмент уровня аккаунта,
        контроль использования маржи.
        """
        # print()
        # cprint(f"ON_TRADE {dt} {instrument} {price}", "cyan")
        # self.portfolio_info()

        # Протестировать новую цену (не добавляя в историю).
        # Получить суммарный объем на покупку/продажу по всем сигналам.
        total_buy, total_sell = self.test_new_price(instrument, dt, price)

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

        if price and side and asset_amount_diff > 0:
            color = "white"
        else:
            color = "cyan"
        symbol_str = colored(f" {instrument} ", color, attrs=["reverse"])
        color = "black"
        if side == "buy":
            color = "green"
        if side == "sell":
            color = "red"
        # Логи: какая операция должна произойти
        txt = (
            f"{dt:%Y-%m-%d %H:%M:%S} {symbol_str} "
            f"current: {current_position:+0.0f}  "
            f"adviced: {advised_position:+0.0f}  "
            f"can buy: {total_buy:0.0f}  "
            f"can sell: {total_sell:0.0f}  //  "
            f"{side} {asset_amount_diff}"
        )
        print()
        cprint(txt)
        # send_telegram(txt)

        # Посчитать, сколько в штуках нужно купить/продать.
        # Проверить, что предлагаемое изменение больше минимального
        if price and side and asset_amount_diff > 0:
            self.trades_count[side] += 1

            assert self.prev_net_value is not None

            # Подсчет gross profit/loss после каждой сделки
            diff_value = self.exchange.net_value - self.prev_net_value
            self.gross_profit += max(0, diff_value)
            self.gross_loss += min(0, diff_value)
            self.prev_net_value = self.exchange.net_value

            if advised_position:
                self.log_trades += f"{dt:%Y-%m-%d %H:%M:%S},{side},{price:0.4f},{diff_value:0.4f}\n"
            else:
                self.log_trades += f"{dt:%Y-%m-%d %H:%M:%S},{side}_close,{price:0.4f},{diff_value:0.4f}\n"
            self.exchange.trade(side, asset_amount_diff, instrument)

            self.on_event("before_interval", dt, instrument)

        # self.portfolio_info()
        # print()

    def test_new_price(self, instrument, dt, price):
        """
        Посчитать суммарный объем покупки и продажи,
        который предлагают советники для новой цены
        """
        # Сумма, которой может управлять один советник
        buying_power = self.exchange.net_value / len(self.advisors)

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
