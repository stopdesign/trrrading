import math
from datetime import datetime
from decimal import Decimal
from termcolor import cprint, colored
from advisor import Advisor
from exchange import BacktestExchange
from strategy import Signal


class Trader:
    def __init__(self):
        cprint("Init trader", "white")

        # Как торговать
        # TODO: это всё нужно брать из конфигов
        self.advisors = [
            Advisor(strategy="ChannelBreakout", length=400, instrument="COPX.ARCA"),
            Advisor(strategy="ChannelBreakout", length=400, instrument="URA.ARCA"),
        ]

        symbols_to_track = list(set([a.instrument for a in self.advisors]))

        dt_start = datetime(2021, 5, 1)

        self.exchange = BacktestExchange(
            symbols=symbols_to_track,
            dt_start=dt_start,
            cash=Decimal("10000"),
        )

        self.max_net_value = Decimal("-Infinity")
        self.cur_drawdown = 0
        self.max_drawdown = Decimal("-Infinity")

        self.portfolio_info()
        print()

    def start(self, loop):
        cprint("Start listening for updates...", "white")
        self.exchange.start_listen(self.on_event, loop)

    def stop(self, loop):
        for instrument in self.exchange.get_positions():
            self.close_position(instrument)
        print()
        cprint(" Result ", attrs=["reverse"])
        self.portfolio_info()
        print()
        cprint(
            f"net: {self.exchange.net_value:0.0f}  "
            f"dd: {self.cur_drawdown:0.1f}%  "
            f"max dd: {self.max_drawdown:0.1f}%  ",
        )

    def on_event(self, event_type, dt, symbol, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        # cprint(f"{dt:%Y-%m-%d %H:%M:%S}: EVENT {event_type}", "white")

        if event_type == "trade":
            self.on_trade(dt, symbol, payload["price"], payload["size"])

        if event_type in ["trade", "trade_before_start"]:
            # Добавление нового значения цены в стратегию
            for advisor in self.advisors:
                if advisor.instrument != symbol:
                    continue
                advisor.strategy.update_trades(
                    {"timestamp": dt.timestamp() * 1000, "price": payload["price"]}
                )
                # Обновить сигнал
                advisor.test_price(payload["price"])

        if event_type == "quote":
            pass
            # self.market_data.on_quote(payload)

        if event_type == "before_interval":
            # Тут выводится статистика на начало интервала
            cprint(
                f"{dt:%Y-%m-%d %H:%M}: EVENT {event_type} "
                f"net: {self.exchange.net_value:0.0f}  "
                f"dd: {self.cur_drawdown:0.1f}%  "
                f"max dd: {self.max_drawdown:0.1f}%  ",
                "white",
            )

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

    def on_trade(self, dt: datetime, instrument, price, volume=None):
        """
        Тут торговля, если стратегия дала сигнал.
        Здесь же риск-менеджмент уровня аккаунта,
        контроль использования маржи.
        """
        # print()
        # cprint(f"ON_TRADE {dt} {symbol} {price}", "cyan")

        # Протестировать новую цену
        total_buy, total_sell = self.test_new_price(instrument, price)

        # Это всё должно быть после тестирования новой цены
        current_position = self.get_current_position(instrument)
        advised_position = self.get_advised_position(instrument)

        diff = advised_position - current_position

        # Всё равно ничего сделать нельзя
        if not (diff and (total_buy or total_sell)):
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
            self.update_position(side, asset_amount_diff, instrument)

        self.portfolio_info()
        print()

    def test_new_price(self, instrument, price):
        # Сумма, которой может управлять один советник
        buying_power = self.exchange.net_value / len(self.advisors)

        total_buy, total_sell = Decimal("0"), Decimal("0")

        for advisor in self.advisors:
            if advisor.instrument != instrument:
                continue

            old_state = advisor.state

            if signal := advisor.test_price(price):
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
