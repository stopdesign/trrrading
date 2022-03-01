import logging
from datetime import datetime, timezone
from decimal import Decimal
from termcolor import cprint, colored
from exchange import BaseExchange
from exchange.mixin import Healthcheck, AccountEvents
from main.models import Order, Instrument, Account, Run
from django.apps import apps

log = logging.getLogger("broker")


class IBWebExchange(BaseExchange, Healthcheck):
    healthcheck_interval = 60
    rel_price_cap = 0.005  # на столько limit price будет хуже mid_price
    price_precision = Decimal("0.01")

    backtest = True

    def __init__(self, instruments: dict, **kwargs):
        super().__init__(instruments, **kwargs)

        # django.setup(set_prefix=False)
        apps.populate(["main"])

        # from main.models import Exchange

        self.cash_initial = kwargs.get("cash", Decimal("10000"))
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
                self.create_order(side, symbol, amount, price, dt)

        else:
            # Увеличение позиции в ту же сторону
            total_value = position["amount"] * position["price"]
            total_value += amount * Decimal(price)
            total_amount = position["amount"] + amount
            av_price = total_value / total_amount

            self.create_order(side, symbol, total_amount, av_price, dt)

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

    def create_order(self, side, symbol, amount, price, dt):

        txt = f"TRADE #order_id: {dt} {side} {symbol} {amount} @ {price}"
        print(colored(txt, color="cyan", attrs=["reverse"]))
        # send_telegram(txt)

        """
        Жизненный цикл ордера

        Перед созданием ордера:
        — заблокировать действия по данному инструменту
        — дернуть обновление ордеров
        — проверить, что нет конфликтующих ордеров и ситуация не изменилась:
            — посмотреть, нет ли неисполненного ордера по этому инструменту
            — если он есть, то новый ордер должен его учитывать (дополнять/отменять)
        — если всё нормально, создать ордер
        — если что-то изменилось — не создавать ордер и сообщить об ошибке

        Проще всего, наверное, отменять существующие ордеры, обновлять базу
        ордеров и позиций, пересчитывать параметры ордера и создавать новый.
        """

        stock_symbol, exchange_symbol = symbol.split(".")
        instrument = Instrument.objects.get(symbol=stock_symbol)

        # Создать запись в базе данных
        account = Account.objects.get(id=1)
        run = Run.objects.last()

        order = Order.market_order(account, run, instrument, str(side).upper(), abs(amount))
        order.signal_price = price

        # Тут эмуляция исполнения ордера при бэктесте
        price1 = self.get_price(symbol, "buy")
        price2 = self.get_price(symbol, "sell")
        price3 = self.get_price(symbol, "mid")
        print(f"PRICE: {price1}, {price2}, {price3}")

        order.filled = abs(amount)
        order.avg_fill_price = price3
        order.save()
        order.created_at = dt.replace(tzinfo=timezone.utc)
        order.save()

        # TODO: размещение ордера
        self.positions[symbol] = {
            "amount": amount,
            "price": price,
        }

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
