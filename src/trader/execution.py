import logging
from datetime import timezone
from decimal import Decimal
from exchange import BaseExchange
from main.models import Instrument, Order
from termcolor import colored

log = logging.getLogger("execution")


class Execution:
    """
    Применение Target Positions к реальному миру.
    """
    exchange: BaseExchange

    def __init__(self, exchange, portfolio, run):
        self.run = run
        self.exchange = exchange
        self.account = run.account
        self.target_positions = portfolio.positions
        self.actual_positions = self.exchange.get_positions()

    def apply_targets(self, dt):

        # что на самом деле есть в портфолио
        self.actual_positions = self.exchange.get_positions()

        for symbol in self.exchange.instruments:
            actual = self.actual_positions.get(symbol, {}).get("amount", 0)
            target = self.target_positions.get(symbol, {}).get("amount", 0)
            signal_price = self.target_positions.get(symbol, {}).get("signal_price", 0)

            # if dt > self.exchange.dt_start:
            #     log.info(f"POSITIONS {symbol} actual={actual} target={target}")

            side = None
            order_amount = abs(actual - target)

            if actual < target:
                side = "buy"
            elif actual > target:
                side = "sell"

            if not side:
                continue

            # Проверить ордеры, которые выставлены и ждут исполнения
            # TODO: в будущем нужно добавлять/отменять ордер в этом случае
            if not self.run.backtest:
                if amount_in_orders := self.get_amount_in_orders(symbol):
                    log.warning(f"Active orders: {symbol} {amount_in_orders}")
                    continue

            order = self.create_order(dt, symbol, side, order_amount, signal_price)

            if self.run.backtest:
                # Здесь эмулируется исполнение ордера

                fill_price = self.exchange.get_price(symbol, "mid")
                fill_price = Decimal(str(fill_price))
                order.simulate_fill(fill_price)

                # где-то тут должно быть фейковое изменение cash и margin used
                # При полном или частичном закрытии позиции считается профит.

                if side == "sell":
                    delta = -order_amount
                else:
                    delta = order_amount

                # Фактическая и желаемая позиции не 0 и имеют разный знак
                amount = delta
                position = self.exchange.positions[symbol]
                trade_profit = 0

                # Позиция и дельта не 0 и имеют разный знак
                if actual * delta < 0:
                    # Частичное закрытие позиции
                    amount_to_close = min(abs(actual), abs(delta))

                    if side == "sell":
                        amount_to_close = -amount_to_close

                    # log.info(f"amount_to_close: {amount_to_close}")

                    # Одно с другим сокращается на partial_close_amount
                    amount -= amount_to_close
                    position["amount"] += amount_to_close

                    # Записать профит от закрытия позиции
                    trade_profit = amount_to_close * (position["price"] - fill_price)
                    self.exchange.cash += trade_profit

                    # # Если amount еще остался — открыть позицию
                    if amount != 0:
                        self.exchange.positions[symbol] = {
                            "amount": amount,
                            "price": fill_price,
                        }
                else:
                    # log.info(f"amount_to_open: {order_amount}")
                    # Увеличение позиции в ту же сторону
                    total_value = position["amount"] * position["price"]
                    total_value += amount * Decimal(fill_price)
                    total_amount = position["amount"] + amount
                    av_price = total_value / total_amount
                    self.exchange.positions[symbol] = {
                        "amount": total_amount,
                        "price": av_price,
                    }

                # Событие «успешное завершение сделки»
                payload = {
                    "side": side,
                    "amount": order_amount,
                    "price": fill_price,
                    "profit": trade_profit,
                    "slippage": 0,
                    "fee": 0,
                    "net_value": self.exchange.net_value,
                }
                self.exchange.on_event("after_trade", dt, symbol, payload)
                print()

    def get_amount_in_orders(self, symbol):
        stock_symbol, exchange_symbol = symbol.split(".")
        instrument = Instrument.objects.get(symbol=stock_symbol)

        orders = Order.objects.filter(account=self.account, instrument=instrument)
        orders = orders.exclude(status__in=["Filled", "Cancelled", "Inactive"])

        in_active_orders = 0
        for order in orders:
            in_active_orders += order.amount - order.filled

        assert in_active_orders >= 0
        return in_active_orders

    def create_order(self, dt, symbol, side, order_amount, signal_price):
        stock_symbol, exchange_symbol = symbol.split(".")
        instrument = Instrument.objects.get(symbol=stock_symbol)

        txt = f"TRADE: {dt}  {side:>4} {symbol} {order_amount} @ {signal_price}"
        log.info(colored(txt, color="cyan"))

        # Шаблон ордера
        order = Order.market_order(
            self.account,
            self.run,
            instrument,
            side.upper(),
            order_amount,
        )
        order.signal_price = signal_price
        order.created_at = dt.replace(tzinfo=timezone.utc)
        order.save()

        return order
