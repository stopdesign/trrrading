import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal
from termcolor import cprint
from exchange import BaseExchange
from data_types import BidAsk, Trade, Margin, Fee
from storage.ib import load_many


class BacktestExchange(BaseExchange):
    backtest = True
    margin = Margin()
    fee = Fee(fixed_rate=0.003)

    def __init__(self, instruments: dict, **kwargs):
        super().__init__(instruments, **kwargs)
        self.dt_from = kwargs.get("dt_from", self.dt_start - timedelta(days=20))
        self.cash_initial = kwargs.get("cash", Decimal("10000"))
        self.cash = self.cash_initial
        self.all_data = pd.DataFrame()

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
        stream = self.all_data.loc[self.dt_start:self.dt_end]
        for row in stream.itertuples():
            self.interval_event(row)
            self.stream_event(row)

    def stop_listen(self):
        self.close_all()

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

    def close_all(self):
        """
        Закрыть все открытые позиции.
        """
        for symbol, position in self.positions.items():
            amount = position["amount"]
            if amount > 0:
                self.trade("sell", abs(amount), symbol, self.dt_last)
            if amount < 0:
                self.trade("buy", abs(amount), symbol, self.dt_last)

    def trade(self, side: str, amount: Decimal, symbol, dt: datetime, sig_price=None):
        """
        Создать ордер на бирже, скорректировать позицию.

        Если открыта позиция и заявка пришла в другую сторону,
        то происходит частичное закрытие, а прибыль материализуется.
        На оставшуюся сумму происходит открытие позиции.

        Если позиция и заявка имеют одно направление,
        то позиция увеличивается на нужную сумму.
        """
        start_amount = amount
        trade_profit = None
        position = self.positions.get(symbol, self.empty_position)
        price = self.get_price(symbol, side)

        if not price:
            cprint(" SKIP TRADE: No price data ", "red", attrs=["reverse"])
            return None, None

        price = Decimal(str(price))

        # Signal price — цена, на которой принято решение о сделке.
        # Используется для подсчета slippage.
        if not sig_price:
            sig_price = Decimal(str(self.get_price(symbol, "mid")))

        fee = self.fee.for_amount(float(amount))
        self.cash -= Decimal(fee)

        if side == "sell":
            amount = -amount

        # Позиция и дельта не 0 и имеют разный знак
        if amount * position["amount"] < 0:
            # Частичное закрытие позиции
            amount_to_close = min(abs(amount), abs(position["amount"]))

            if side == "sell":
                amount_to_close = -amount_to_close

            # Одно с другим сокращается на partial_close_amount
            amount -= amount_to_close
            position["amount"] += amount_to_close

            # Записать профит
            trade_profit = amount_to_close * (position["price"] - price)
            self.cash += trade_profit

            # Если amount еще остался — открыть позицию
            if amount != 0:
                self.positions[symbol] = {
                    "amount": amount,
                    "price": price,
                }
        else:
            # Увеличение позиции в ту же сторону
            total_value = position["amount"] * position["price"]
            total_value += amount * Decimal(price)
            total_amount = position["amount"] + amount
            av_price = total_value / total_amount
            self.positions[symbol] = {
                "amount": total_amount,
                "price": av_price,
            }

        slippage = abs(float(sig_price) - float(price)) * float(start_amount)

        # Событие «успешное завершение сделки»
        payload = {
            "side": side,
            "amount": start_amount,
            "price": price,
            "profit": trade_profit,
            "slippage": slippage,
            "fee": fee,
            "net_value": self.net_value,
        }
        self.on_event("after_trade", dt, symbol, payload)

        return price, start_amount

    @property
    def net_value(self):
        """
        Суммарное количество бабла депозита: кэш плюс стоимость активов.
        """
        total_value = self.cash
        for symbol, position in self.positions.items():
            mid = Decimal(str(self.get_price(symbol, "mid")))
            total_value += position["amount"] * (mid - position["price"])
        return total_value
