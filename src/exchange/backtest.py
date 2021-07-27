from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from termcolor import cprint, colored
from exchange import BaseExchange
from storage.ib import load_many


@dataclass
class Trade:
    price: float
    volume: int


@dataclass
class BidAsk:
    bid: float
    ask: float


class BacktestExchange(BaseExchange):
    def __init__(self, symbols: list, **kwargs):
        super().__init__(symbols)
        self.quotes = {}
        self.dt_start = kwargs.pop("dt_start")
        self.dt_from = kwargs.get("dt_from", self.dt_start - timedelta(days=5))
        self.cash_initial = kwargs.get("cash", Decimal("10000"))
        self.cash = self.cash_initial
        self.fee_rate = Decimal("0.02")
        self.all_data = self.load_data()

    def load_data(self):
        df = load_many(self.symbols, ["TRADES", "BIDASK"], start=self.dt_from.date())

        # BIDASK должен приходить раньше TRADES для этого интервала
        df.sort_values(["date", "ticker", "data_type"], inplace=True)

        return df

    def process_historical_data(self, on_event):
        """
        Прогнать события по историческим данным.
        """
        stream = self.all_data.loc[self.dt_from:self.dt_start]
        for row in stream.itertuples():
            self.process_event(row, on_event)

    def start_listen(self, on_event, loop=None):
        """
        Эмулировать события, приходящие с биржи.
        """
        stream = self.all_data.loc[self.dt_start:]
        prev_date = None
        for row in stream.itertuples():
            dt = row.Index.to_pydatetime()
            if prev_date and dt.hour != prev_date.hour:
                norm_dt = dt.replace(minute=0, second=0, microsecond=0)
                on_event("before_interval", norm_dt)
            prev_date = dt
            self.process_event(row, on_event)

    def process_event(self, row, on_event):
        dt = row.Index.to_pydatetime()
        symbol = row.ticker

        if row.data_type == "BIDASK":
            payload = BidAsk(bid=row.av_bid, ask=row.av_ask)
            on_event("quote", dt, symbol, payload)

        if row.data_type == "TRADES":
            for price in [row.open, row.high, row.low, row.close]:
                payload = Trade(price=price, volume=row.volume)
                on_event("trade", dt, symbol, payload)
            on_event("bar", dt, symbol, row)

    def stop_listen(self, loop=None):
        """
        Позакрывать все позиции.
        """
        for symbol, position in self.positions.items():
            if position["amount"] > 0:
                self.trade("sell", abs(position["amount"]), symbol)
            if position["amount"] < 0:
                self.trade("buy", abs(position["amount"]), symbol)

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

    def trade(self, side: str, amount: Decimal, symbol: str):
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

                txt = f"Close {partial_close_amount} {symbol} "

                color = "white"
                if trade_profit > 0:
                    color = "green"
                if trade_profit < 0:
                    color = "red"
                rel_profit = (trade_profit / self.cash) * 100
                self.cash += trade_profit

                txt += colored(f" {trade_profit:+0.2f} ", color, attrs=["reverse"])
                txt += colored(f"{rel_profit:+0.2f}% ", color, attrs=["reverse"])
                txt += colored(f" Σ {self.cash:0.0f} ", "white", attrs=["reverse"])
                # print(txt)

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
                    # "dt": position["dt"],
                    "amount": total_amount,
                    "price": av_price,
                }

            return price, start_amount
        else:
            cprint(" SKIP TRADE: Not enough quote data ", "red", attrs=["reverse"])
            return None, None

    def get_positions(self):
        return self.positions
