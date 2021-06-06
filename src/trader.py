import math
from datetime import datetime
from decimal import Decimal
from termcolor import cprint, colored
from advisor import Advisor
from exchange import BacktestExchange
from market_data import MarketData
from strategy import Signal


class Trader:
    def __init__(self):
        cprint("Init trader", "white")

        # Как торговать
        # TODO: это всё нужно брать из конфигов
        self.advisors = [
            Advisor(strategy="ChannelBreakout", length=400, instrument="COPX.ARCA"),
            # Advisor(strategy="ChannelBreakout", length=400, instrument="URA.ARCA"),
        ]

        symbols_to_track = list(set([a.instrument for a in self.advisors]))
        max_length = 1

        # Переименовать в broker?
        self.exchange = BacktestExchange(
            symbols=symbols_to_track,
            dt_from=datetime(2021, 5, 1),
            cash=Decimal("10000"),
        )

        self.market_data = MarketData(
            symbols=symbols_to_track,
            timeframe=60,
            exchange=self.exchange,
        )

        # # Подгрузить исторические данные по отслеживаемым инструментам
        # print("Get historical data...")
        # self.market_data.get_historical_data(length=max_length)
        # for k, v in self.market_data.historical.items():
        #     cprint(f"{k}: {len(v)} intervals", "white")
        # print()
        #
        # # Просунуть исторические данные в адвайзеров
        # print("Advisors:")
        # for advisor in self.advisors:
        #     trades = self.market_data.historical[advisor.instrument]
        #     print(len(trades))
        #     last_signal = None
        #     for trade in trades:
        #         signal = advisor.test_price(trade)
        #         if signal in [Signal.LONG, Signal.SHORT]:
        #             last_signal = signal
        #     advisor.state = last_signal
        #     cprint(f"{advisor}, state: {last_signal}", "white")
        # print()

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

    def on_event(self, event_type, dt, symbol, payload):
        """
        В стриме биржи возникло новое событие.
        """
        # cprint(f"{dt:%Y-%m-%d %H:%M:%S}: EVENT {event_type}", "white")

        if event_type == "trade":
            self.on_trade(dt, symbol, payload["price"], payload["size"])
            # self.market_data.on_trade(payload)

        if event_type == "quote":
            pass
            # self.market_data.on_quote(payload)

        # тут обработка аналитических событий

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
                "blue"
            )
        cprint(
            f"CASH: {self.exchange.cash:0.0f},  "
            f"VALUE: {self.exchange.net_value:0.0f}",
            "green"
        )

    def get_current_position(self, symbol):
        # TODO: перенести в exchange?
        positions = self.exchange.get_positions()
        return positions.get(symbol, BacktestExchange.empty_position)["amount"]

    def on_trade(self, dt: datetime, symbol, price, volume=None):
        """
        Тут торговля, если стратегия дала сигнал.
        Здесь же риск-менеджмент уровня аккаунта,
        контроль использования маржи.
        """
        # print()
        # cprint(f"ON_TRADE {dt} {symbol} {price}", "cyan")

        instrument = symbol

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

            # Добавление нового значения в стратегию
            advisor.strategy.update_trades({
                "timestamp": dt.timestamp() * 1000,
                "price": price
            })

        # Это всё должно быть после тестирования новой цены
        current_position = self.get_current_position(instrument)
        advised_position = self.get_advised_position(instrument)

        diff = advised_position - current_position

        # Всё равно ничего сделать нельзя
        if not (diff and (total_buy or total_sell)):
            # cprint("SKIP", "white")
            return

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
        txt = (
            f"{dt:%Y-%m-%d %H:%M} "
            f"{symbol_str} "
            f"current: {current_position:+0.0f}  "
            f"adviced: {advised_position:+0.0f}  "
            f"can buy: {total_buy:0.0f}  "
            f"can sell: {total_sell:0.0f}  //  "
            f"{side} {asset_amount_diff}"
        )
        print()
        print(txt)

        # Посчитать, сколько в штуках нужно купить/продать.
        # Проверить, что предлагаемое изменение больше минимального
        if price and side and asset_amount_diff > 0:
            self.update_position(side, asset_amount_diff, instrument)

        self.portfolio_info()
        print()

    def close_position(self, instrument):
        position = self.get_current_position(instrument)
        if position > 0:
            self.update_position("sell", abs(position), instrument)
        if position < 0:
            self.update_position("buy", abs(position), instrument)

    def update_position(self, side, asset_amount_diff, instrument):
        """
        Синхронно создать ордер и дождаться исполнения.
        Обновить данные о портфолио.
        """
        self.exchange.trade(side, asset_amount_diff, instrument)
