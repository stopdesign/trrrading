import sys
import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from termcolor import cprint, colored
from advisor import Advisor
from exchange import BacktestExchange, ExanteExchange
from strategy import Signal
from util import interval_dt, parse_quote, reformat_ohlc
import pandas_market_calendars as mcal


CURSOR_UP_ONE = '\x1b[1A'
ERASE_LINE = '\x1b[2K'


class Trader:
    def __init__(self):
        cprint("Init trader", "white")

        self.log_intervals = "Date,Open,High,Low,Close\n"
        self.log_trades = "Date,Direction,Price\n"

        # Как торговать
        self.advisors = [
            Advisor(strategy="ChBr", length=2, instrument="COPX.ARCA"),  # 70 / 17.1
            # Advisor(strategy="ChBr", length=480, instrument="COPX.ARCA"),  # 86 / 16.7
            # Advisor(strategy="ChBr", length=300, instrument="URA.ARCA"),   # 26 / 20.0
            # Advisor(strategy="ChBr", length=430, instrument="URA.ARCA"),   # 61 / 17.8
        ]

        track = list(set([a.instrument for a in self.advisors]))

        dt = datetime(2021, 1, 1)  # noqa

        self.schedule = {}
        for symbol in track:
            exchange = symbol.split(".")[1]
            exchange = exchange.replace("ARCA", "NYSE")
            cal = mcal.get_calendar(exchange)
            start_date = dt - timedelta(days=20)
            end_date = datetime.utcnow() + timedelta(days=300)
            schedule = cal.schedule(start_date=start_date, end_date=end_date)
            schedule_by_day = {}
            for day, t in sorted(schedule.T.to_dict("list").items()):
                t0, t1 = t[0].to_pydatetime(), t[1].to_pydatetime()
                schedule_by_day[day.date()] = [t0, t1]
            self.schedule[symbol] = schedule_by_day

        # self.exchange = BacktestExchange(track, dt_start=dt, cash=Decimal("10000"))
        self.exchange = ExanteExchange(track)

        # Получить из биржи исторические данные
        # по сделкам за период до начала торгов
        for symbol in track:
            print()
            now = datetime.now().astimezone(timezone.utc)
            data = self.exchange.fetch_backtest_data(symbol, now, 60)
            for advisor in self.advisors:
                if advisor.instrument != symbol:
                    continue
                print()
                cprint(f"Updating {advisor}", "white")
                for event in data:
                    event_dt = interval_dt(event)
                    if "price" in event:
                        # Обновить текущий внутренний state стратегии
                        advisor.test_price(event_dt, Decimal(event["price"]))
                        # Добавить новую цену
                        advisor.strategy.update_trades(event)
                    if "ask" in event and "bid" in event:
                        # Добавить в биржу данные о ценах
                        self.exchange.quotes[symbol] = {
                            "ask": list(map(parse_quote, event["ask"])),
                            "bid": list(map(parse_quote, event["bid"])),
                            "dt": interval_dt(event),
                        }

        self.max_net_value = Decimal("-Infinity")
        self.max_drawdown = Decimal("-Infinity")
        self.cur_drawdown = 0

        print()
        self.portfolio_info()
        print()

    def start(self, loop):
        cprint("Start listening for updates...", "white")
        self.exchange.start_listen(self.on_event, loop)

    def stop(self, loop):  # noqa
        self.exchange.stop_listen()
        print()
        cprint(" Result ", attrs=["reverse"])
        self.portfolio_info()
        print()
        cprint(
            f"net: {self.exchange.net_value:0.0f}  "
            f"dd: {self.cur_drawdown:0.1f}%  "
            f"max dd: {self.max_drawdown:0.1f}%  ",
        )

        with open("trades.csv", "w") as t:
            t.write(self.log_trades)

        for advisor in self.advisors:
            data = advisor.strategy.historical
            data = reformat_ohlc(data, 3600)

            for interval in data:
                dt = interval_dt(interval)
                log = "{open},{high},{low},{close}\n".format(**interval)
                self.log_intervals += f"{dt:%Y-%m-%d %H:%M:%S},{log}"

        with open("data.csv", "w") as d:
            d.write(self.log_intervals)

    def on_event(self, event_type, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        # cprint(f"{dt:%Y-%m-%d %H:%M:%S}: EVENT {event_type} {symbol}", "white")

        if event_type == "trade":
            self.on_trade(dt, symbol, payload["price"], payload["size"])

        # Это должно происходить после запуска on_trade
        if event_type in ["trade", "trade_before_start"]:
            # Добавление нового значения цены в стратегию
            for advisor in self.advisors:
                if advisor.instrument != symbol:
                    continue
                advisor.strategy.update_trades(
                    {"timestamp": dt.timestamp() * 1000, "price": payload["price"]}
                )
                # Обновить текущий внутренний state стратегии
                advisor.test_price(dt, payload["price"])

        if event_type == "quote":
            pass

        if event_type == "before_interval":
            # Тут выводится статистика на начало интервала
            sys.stdout.write(CURSOR_UP_ONE)
            sys.stdout.write(ERASE_LINE)
            cprint(
                f"{dt:%Y-%m-%d %H:%M:%S}: "
                f"net: {self.exchange.net_value:0.0f}  "
                f"dd: {self.cur_drawdown:0.1f}%  "
                f"max dd: {self.max_drawdown:0.1f}%  ",
                "white",
            )

            track = list(set([a.instrument for a in self.advisors]))
            for symbol in track:
                t0, t1 = self.schedule[symbol][dt.date()]
                is_open = t0 and t1 and t0 < dt.astimezone(timezone.utc) < t1
                status_str = "OPEN" if is_open else "CLOSED"
                print(f"{dt:%Y-%m-%d %H:%M:%S}: {symbol}, {status_str}")

        if event_type == "after_event":
            # Обновление статистики
            if self.exchange.net_value > self.max_net_value:
                self.max_net_value = self.exchange.net_value
            drawdown = self.max_net_value - self.exchange.net_value
            self.cur_drawdown = drawdown / self.max_net_value * 100
            self.max_drawdown = max(self.max_drawdown, self.cur_drawdown)

    def get_advised_position(self, instrument):
        res = Decimal("0")
        buying_power = self.exchange.net_value / len(self.advisors)
        for advisor in self.advisors:
            if advisor.instrument != instrument:
                continue
            if advisor.state == Signal.LONG:
                price = self.exchange.get_price(instrument, "buy")
                amount = math.floor(buying_power / price)
                res += amount
            if advisor.state == Signal.SHORT:
                price = self.exchange.get_price(instrument, "sell")
                amount = math.floor(buying_power / price)
                res -= amount

        # Если нельзя шортить
        res = max(Decimal(0), res)

        return res

    def portfolio_info(self):
        """
        Состояние портфолио.
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

    def get_current_position(self, symbol):
        # TODO: перенести в exchange?
        positions = self.exchange.get_positions()
        return positions.get(symbol, BacktestExchange.empty_position)["amount"]

    def on_trade(self, dt: datetime, instrument, price, volume=None):  # noqa
        """
        Тут торговля, если стратегия дала сигнал.
        Здесь же риск-менеджмент уровня аккаунта,
        контроль использования маржи.
        """
        print()
        cprint(f"ON_TRADE {dt} {instrument} {price}", "cyan")

        self.portfolio_info()

        # Протестировать новую цену
        total_buy, total_sell = self.test_new_price(instrument, dt, price)

        # Это всё должно быть после тестирования новой цены
        current_position = self.get_current_position(instrument)
        advised_position = self.get_advised_position(instrument)

        diff = advised_position - current_position

        # Всё равно ничего сделать нельзя
        if not (diff and (total_buy or total_sell)):
            cprint(f"SKIP: diff: {diff}, total_buy: {total_buy}, total_sell: {total_sell}")
            return

        # Посчитать, куда нужно торговать,
        # и на какой объем есть сигнал
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
        print(
            f"\n{dt:%Y-%m-%d %H:%M} {symbol_str} "
            f"current: {current_position:+0.0f}  "
            f"adviced: {advised_position:+0.0f}  "
            f"can buy: {total_buy:0.0f}  "
            f"can sell: {total_sell:0.0f}  //  "
            f"{side} {asset_amount_diff}"
        )

        # Посчитать, сколько в штуках нужно купить/продать.
        # Проверить, что предлагаемое изменение больше минимального
        if price and side and asset_amount_diff > 0:
            self.log_trades += f"{dt:%Y-%m-%d %H:%M:%S},{side},{price:0.2f}\n"
            self.update_position(side, asset_amount_diff, instrument)

        self.portfolio_info()
        print()

    def test_new_price(self, instrument, dt, price):
        # Сумма, которой может управлять один советник
        buying_power = self.exchange.net_value / len(self.advisors)

        total_buy, total_sell = Decimal("0"), Decimal("0")

        for advisor in self.advisors:
            if advisor.instrument != instrument:
                continue

            old_state = advisor.state

            if signal := advisor.test_price(dt, price):
                if signal == Signal.LONG:
                    cur_price = self.exchange.get_price(instrument, "buy")
                    amount = math.floor(buying_power / cur_price)
                    if old_state == Signal.SHORT:
                        total_buy += amount * 2
                    elif old_state == Signal.LONG:
                        total_buy += 0
                    else:
                        total_buy += amount
                if signal == Signal.SHORT:
                    cur_price = self.exchange.get_price(instrument, "sell")
                    amount = math.floor(buying_power / cur_price)
                    if old_state == Signal.LONG:
                        total_sell += amount * 2
                    elif old_state == Signal.SHORT:
                        total_sell += 0
                    else:
                        total_sell += amount

        return total_buy, total_sell

    def close_position(self, instrument):
        position = self.get_current_position(instrument)
        if position > 0:
            self.update_position("sell", abs(position), instrument)
        if position < 0:
            self.update_position("buy", abs(position), instrument)

    def update_position(self, side, asset_amount_diff, instrument):
        self.exchange.trade(side, asset_amount_diff, instrument)
