from datetime import datetime
from decimal import Decimal
from termcolor import cprint
from exchange import BaseExchange
from data_types import Margin, Fee


class BacktestExchange(BaseExchange):
    backtest = True
    margin = Margin()
    fee = Fee(fixed_rate=0.003)

    def __init__(self, instruments: dict, **kwargs):
        super().__init__(instruments, **kwargs)
        self.cash_initial = kwargs.get("cash", Decimal("100000"))
        self.cash = self.cash_initial

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
