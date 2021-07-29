import logging
import pandas as pd
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from termcolor import cprint, colored
from exchange import BaseExchange
from storage.ib import load_many


log = logging.getLogger("backtest")


@dataclass
class Trade:
    price: float
    volume: int


@dataclass
class BidAsk:
    bid: float
    ask: float


class BacktestExchange(BaseExchange):
    def __init__(self, advisors: list, **kwargs):
        super().__init__(advisors)
        self.quotes = {}
        self.dt_start = kwargs.pop("dt_start")
        self.dt_from = kwargs.get("dt_from", self.dt_start - timedelta(days=5))
        self.cash_initial = kwargs.get("cash", Decimal("10000"))
        self.cash = self.cash_initial
        self.fee_rate = Decimal("0.02")
        self.symbols = list(set([a.instrument for a in self.advisors]))
        self.all_data = pd.DataFrame()
        self.dt_last = None

    def load_data(self):
        df = load_many(self.symbols, ["TRADES", "BIDASK"], start=self.dt_from.date())
        # BIDASK должен приходить раньше TRADES для этого интервала
        return df.sort_values(["date", "ticker", "data_type"])

    def warm_up(self):
        """
        Прогнать события по историческим данным.
        """
        self.all_data = self.load_data()

        stream = self.all_data.loc[self.dt_from:self.dt_start]
        for row in stream.itertuples():
            self.stream_event(row)

    def start_listen(self):
        """
        Эмулировать события, приходящие с биржи.
        """
        stream = self.all_data.loc[self.dt_start:]
        for row in stream.itertuples():
            self.interval_event(row)
            self.stream_event(row)

    def stop_listen(self):
        """
        Позакрывать все позиции.
        """
        # The last known date
        for symbol, position in self.positions.items():
            amount = position["amount"]
            if amount > 0:
                self.trade("sell", abs(amount), symbol, self.dt_last)
            if amount < 0:
                self.trade("buy", abs(amount), symbol, self.dt_last)

    def interval_event(self, row):
        """
        Запустить интервальное событие при необходимости.
        """
        dt = row.Index.to_pydatetime()
        if self.dt_last and dt.hour != self.dt_last.hour:
            norm_dt = dt.replace(minute=0, second=0, microsecond=0)
            if dt.day != self.dt_last.day:
                norm_dt = norm_dt.replace(hour=0)
                self.on_event("day", norm_dt)
            else:
                self.on_event("hour", norm_dt)
        self.dt_last = dt

    def stream_event(self, row):
        dt = row.Index.to_pydatetime()
        symbol = row.ticker

        if row.data_type == "BIDASK":
            payload = BidAsk(bid=row.av_bid, ask=row.av_ask)
            self.on_event("quote", dt, symbol, payload)

        if row.data_type == "TRADES":
            for price in [row.open, row.high, row.low, row.close]:
                payload = Trade(price=price, volume=row.volume)
                self.on_event("trade", dt, symbol, payload)
            self.on_event("bar", dt, symbol, row)

    def get_price(self, symbol: str, side: str) -> Optional[float]:
        if quotes := self.quotes.get(symbol):
            if side == "sell":
                return quotes["bid"]
            if side == "buy":
                return quotes["ask"]

    def add_quote(self, dt, symbol, payload):
        """
        Сохранить BID и ASK как актуальное состояние стакана на бирже.
        """
        current_quote = self.quotes.get(symbol)
        if current_quote and current_quote["dt"] > dt:
            return
        if symbol not in self.quotes:
            self.quotes[symbol] = {}
        # ask и bid могут приходить независимо
        if payload.ask:
            self.quotes[symbol]["ask"] = payload.ask
            self.quotes[symbol]["dt"] = dt
        if payload.bid:
            self.quotes[symbol]["bid"] = payload.bid
            self.quotes[symbol]["dt"] = dt

    def trade(self, side: str, amount: Decimal, symbol: str, dt: datetime):
        """
        Создать ордер на бирже, скорректировать позицию.
        """
        if side == "sell":
            color = "red"
        else:
            color = "green"
        # cprint(f"TRADE: {side} {symbol} {amount}", color)

        assert amount != 0

        start_amount = amount

        if price := Decimal(self.get_price(symbol, side)):
            self.cash -= self.fee_rate * amount

            if side == "sell":
                amount = -amount

            position = self.positions.get(symbol, self.empty_position)

            trade_profit = None

            # Если открыта позиция и заявка пришла в другую сторону,
            # то происходит частичное закрытие, а прибыль материализуется.
            # На оставшуюся сумму происходит открытие позиции.

            # Если позиция и заявка имеют одно направление,
            # то позиция увеличивается на нужную сумму.

            # Позиция и дельта не 0 и имеют разный знак
            if amount * position["amount"] < 0:
                # Частичное закрытие позиции
                partial_close_amount = min(abs(amount), abs(position["amount"]))

                # Сократить позицию
                if position["amount"] >= 0:
                    position["amount"] -= partial_close_amount
                    trade_profit = partial_close_amount * (price - position["price"])
                else:
                    position["amount"] += partial_close_amount
                    trade_profit = partial_close_amount * (position["price"] - price)

                # Сократить требование
                if amount >= 0:
                    amount -= partial_close_amount
                else:
                    amount += partial_close_amount

                # Одно или другое должно сократиться полностью
                assert amount == 0 or position["amount"] == 0

                self.cash += trade_profit

                txt = ""  # f"Close {partial_close_amount} {symbol}  "

                color = "white"
                if trade_profit > 0:
                    color = "green"
                if trade_profit < 0:
                    color = "red"
                rel_profit = (trade_profit / self.cash) * 100

                txt += colored(f"Σ {self.cash:0.0f}  ", "grey")
                txt += colored(f"{trade_profit:+0.2f}  ", color)
                txt += colored(f"{rel_profit:+0.2f}%  ", color)
                log.info(txt)

                # Если amount еще остался — открыть позицию
                if amount != 0:
                    self.positions[symbol] = {
                        "amount": amount,
                        "price": price,
                    }
            else:
                # Увеличение позиции в ту же сторону
                total_value = position["amount"] * position["price"] + amount * Decimal(price)
                total_amount = position["amount"] + amount
                av_price = total_value / total_amount
                self.positions[symbol] = {
                    "amount": total_amount,
                    "price": av_price,
                }

            # Событие «успешное завершение сделки»
            payload = {
                "side": side,
                "amount": start_amount,
                "price": price,
                "profit": trade_profit,
            }
            self.on_event("after_trade", dt, symbol, payload)
            return price, start_amount
        else:
            cprint(" SKIP TRADE: Not enough quote data ", "red", attrs=["reverse"])
            return None, None

    def get_positions(self):
        return self.positions

    @property
    def net_value(self):
        """
        Суммарное количество бабла депозита: кэш плюс стоимость активов.
        """
        total_value = self.cash
        for symbol, position in self.positions.items():
            if position["amount"] > 0:
                price = Decimal(self.get_price(symbol, "sell"))
                if price is None:
                    # FIXME:
                    cprint(f"WARNING: {symbol} price is {price}", "yellow")
                    continue
                total_value += position["amount"] * (price - position["price"])
                total_value -= self.fee_rate * position["amount"]
            if position["amount"] < 0:
                price = Decimal(self.get_price(symbol, "buy"))
                if price is None:
                    cprint(f"WARNING: {symbol} price is {price}", "yellow")
                    continue
                total_value += position["amount"] * (price - position["price"])
                total_value -= self.fee_rate * position["amount"]
        return total_value
