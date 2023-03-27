from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Position:
    sid: str
    capital: Decimal
    amount: Decimal = Decimal("nan")
    avg_price: Decimal = Decimal("nan")
    profit: Decimal = Decimal(0)  # реализованный профит без учета slippage
    max_profit: Decimal = Decimal(0)
    cur_drawdown: Decimal = Decimal(0)  # просадка между сделками, %
    max_drawdown: Decimal = Decimal(0)

    def update(self, amount: Decimal, price: Decimal):

        trade_profit = Decimal(0)

        # Если раньше позиции никакой не было, то считаем её нулевой
        if self.amount.is_nan():
            self.amount = Decimal(0)

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

            self.max_profit = max(self.max_profit, self.profit)

            # Просадка сразу считается относительно капитала,
            # т.к. капитал когда-нибудь сможет меняться
            self.cur_drawdown = (self.max_profit - self.profit) / self.capital
            self.max_drawdown = max(self.max_drawdown, self.cur_drawdown)

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
