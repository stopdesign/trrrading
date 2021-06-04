import math
from decimal import Decimal
from typing import NoReturn
from termcolor import cprint
from advisor import Advisor
from broker import Broker
from market_data import MarketData
from strategy import Signal


class Trader:
    def __init__(self):
        cprint("Init trader", "white")

        # Как торговать
        # TODO: это всё нужно брать из конфигов
        self.advisors = [
            Advisor(strategy="ChannelBreakout", length=1,   instrument="BAC.NYSE"),
            Advisor(strategy="ChannelBreakout", length=10,  instrument="BAC.NYSE"),
            Advisor(strategy="ChannelBreakout", length=1,   instrument="EEM.ARCA"),
            Advisor(strategy="ChannelBreakout", length=10,  instrument="EEM.ARCA"),
            Advisor(strategy="ChannelBreakout", length=1,   instrument="GDX.ARCA"),
            Advisor(strategy="ChannelBreakout", length=10,  instrument="GDX.ARCA"),
        ]

        symbols_to_track = ["GDX.ARCA", "BAC.NYSE", "EEM.ARCA"]
        max_length = 200

        # TODO: передать брокеру, какие инструменты нужно мониторить
        self.broker = Broker(symbols=symbols_to_track)

        self.market_data = MarketData(
            symbols=symbols_to_track, timeframe=60, post=["ChannelBreakout"]
        )

        # Подгрузить исторические данные по отслеживаемым инструментам
        print("Get historical data...")
        self.market_data.get_historical_data(length=max_length)
        for k, v in self.market_data.historical.items():
            cprint(f"{k}: {len(v)} intervals", "white")
        print()

        # Просунуть исторические данные в адвайзеров
        print("Advisors:")
        for advisor in self.advisors:
            trades = self.market_data.historical[advisor.instrument]
            last_signal = None
            for trade in trades:
                signal = advisor.test_price(trade)
                if signal in [Signal.LONG, Signal.SHORT]:
                    last_signal = signal
            advisor.state = last_signal
            cprint(f"{advisor}, state: {last_signal}", "white")
        print()

        self.portfolio_info()
        print()

    def start(self, loop):
        cprint("Start listening for updates...", "white")
        self.broker.exchange.on_trade = lambda x: self.on_event("trade", data=x)
        self.broker.exchange.on_quote = lambda x: self.on_event("quote", data=x)
        self.broker.exchange.start_listen(loop)

    def on_event(self, event_type, **params):
        # cprint(f"ON EVENT {event_type}", "white")
        if event_type == "trade":
            self.on_trade(params["data"])
            self.market_data.on_trade(params["data"])

    def get_advised_position(self, instrument):
        res = Decimal("0")
        buying_power = self.broker.cash / len(self.advisors)
        for advisor in self.advisors:
            if advisor.instrument != instrument:
                continue
            if advisor.state == Signal.LONG:
                price = self.market_data.get_price(instrument, "buy")
                amount = math.floor(buying_power / price)
                res += amount
            if advisor.state == Signal.SHORT:
                price = self.market_data.get_price(instrument, "sell")
                amount = math.floor(buying_power / price)
                res -= amount
        return res

    def portfolio_info(self):
        """
        Состояние портфолио.
        """
        instruments = set()
        for advisor in self.advisors:
            instruments.add(advisor.instrument)
        for instrument in instruments:
            current_position = self.broker.get_current_position(instrument)
            advised_position = self.get_advised_position(instrument)
            cprint(
                f"{instrument:<12} "
                f"current: {current_position:+0.0f}  "
                f"advised: {advised_position:+0.0f}  ",
                "blue"
            )

    def on_trade(self, trade: dict) -> NoReturn:
        """
        Тут торговля, если стратегия дала сигнал.
        Здесь же риск-менеджмент уровня аккаунта,
        контроль использования маржи.
        """
        # print()
        # cprint(f"ON_TRADE {trade}", "cyan")

        instrument = trade["symbolId"]

        # Доля депозита, которой может управлять один советник
        # power = Decimal("1.0") / len(self.advisors)
        buying_power = self.broker.cash / len(self.advisors)

        total_buy, total_sell = Decimal("0"), Decimal("0")

        for advisor in self.advisors:
            if advisor.instrument != instrument:
                continue
            old_state = advisor.state
            if signal := advisor.test_price(trade):
                if signal == Signal.LONG:
                    price = self.market_data.get_price(instrument, "buy")
                    amount = math.floor(buying_power / price)
                    if old_state == Signal.SHORT:
                        total_buy += amount * 2
                    elif old_state == Signal.LONG:
                        total_buy += 0
                    else:
                        total_buy += amount
                if signal == Signal.SHORT:
                    price = self.market_data.get_price(instrument, "sell")
                    amount = math.floor(buying_power / price)
                    if old_state == Signal.LONG:
                        total_sell += amount * 2
                    elif old_state == Signal.SHORT:
                        total_sell += 0
                    else:
                        total_sell += amount

        # Это всё должно быть после тестирования новой цены
        current_position = self.broker.get_current_position(instrument)
        advised_position = self.get_advised_position(instrument)

        diff = advised_position - current_position

        # Всё равно ничего сделать нельзя
        if not (diff and (total_buy or total_sell)):
            return

        side = None
        asset_amount_diff = 0
        if diff > 0:
            asset_amount_diff = min(abs(diff), total_buy)
            side = "buy"
        elif diff < 0:
            asset_amount_diff = min(abs(diff), total_sell)
            side = "sell"

        if side and asset_amount_diff > 0:
            color = "blue"
        else:
            color = "cyan"
        cprint(
            f"{instrument:<12} "
            f"current: {current_position:+0.0f}  "
            f"advised: {advised_position:+0.0f}  "
            f"total_buy: {total_buy:0.0f}  "
            f"total_sell: {total_sell:0.0f}  //  "
            f"{side} {asset_amount_diff}",
            color
        )
        print()

        # Посчитать, сколько в штуках нужно купить/продать.
        # Проверить, что предлагаемое изменение больше минимального
        if side and asset_amount_diff > 0:
            self.broker.adjust_portfolio(side, asset_amount_diff, instrument)

        print()
        print()
