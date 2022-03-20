from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Position:
    symbol: str
    amount: Decimal = Decimal(0)
    avg_price: Decimal = Decimal("nan")
    profit: Decimal = Decimal(0)  # реализованный профит без учета slippage

    def update(self, amount: Decimal, price: Decimal):

        trade_profit = Decimal(0)

        if self.amount == amount:
            return trade_profit

        delta = amount - self.amount

        # Позиция и дельта не 0 и имеют разный знак
        if delta * self.amount < 0:
            # Частичное закрытие позиции
            amount_to_close = min(abs(delta), abs(self.amount))

            # Позиция есть, значит должна быть и цена
            assert not self.avg_price.is_nan()

            # Продажа
            if amount < self.amount:
                amount_to_close = -amount_to_close

            # Одно с другим сокращается на partial_close_amount
            delta -= amount_to_close
            self.amount += amount_to_close

            # Записать профит
            trade_profit = amount_to_close * (self.avg_price - price)
            self.profit += trade_profit

            # Если amount еще остался — открыть позицию
            if delta != 0:
                self.amount = delta
                self.avg_price = price

        else:
            # Увеличение позиции в ту же сторону
            total_value = Decimal(0)
            if self.amount != 0:
                assert not self.avg_price.is_nan()
                total_value += self.amount * self.avg_price
            total_value += delta * price

            self.amount = amount
            self.avg_price = total_value / amount

        return trade_profit
