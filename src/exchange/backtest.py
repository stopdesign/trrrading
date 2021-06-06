from datetime import datetime, timedelta
from decimal import Decimal
import pandas_market_calendars as mcal
from termcolor import cprint
from exchange import BaseExchange
from util import interval_dt, load_from_file, parse_quote


class BacktestExchange(BaseExchange):

    empty_position = {"amount": Decimal("0"), "price": Decimal("0")}

    def __init__(self, symbols: list, **kwargs):
        super().__init__(symbols)

        self.quotes = {}

        self.dt_start = kwargs.get("dt_start", datetime(2021, 1, 5))
        self.dt_from = self.dt_start - timedelta(days=5)
        self.cash_initial = kwargs.get("cash", Decimal(10_000))
        self.cash = self.cash_initial
        self.fee = Decimal("0.02")

    def load_tick_data(self, symbol, dt_from):
        """
        Чтение архивных данных из файлов.
        """
        quotes_file = f"../data/live-{symbol}-quotes-ticks.jsonl"
        trades_file = f"../data/live-{symbol}-trades-ticks.jsonl"

        cprint(f" Load ticks: {dt_from}, {symbol} ", attrs=["reverse"])

        try:
            quotes = load_from_file(quotes_file, dt_from)
        except FileNotFoundError:
            cprint("No quotes data", "red")
            print()
            quotes = []

        trades = load_from_file(trades_file, dt_from)

        # Расписание биржи
        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(start_date=dt_from, end_date=datetime.utcnow())
        schedule_dict = {}
        for day, t in schedule.T.to_dict("list").items():
            schedule_dict[day.date()] = [t[0].timestamp(), t[1].timestamp()]

        # Разметить нерабочее время
        for trade in trades:
            ts = trade["timestamp"] / 1000
            is_open = False
            if day := schedule_dict.get(datetime.utcfromtimestamp(ts).date()):
                is_open = day[0] <= ts < day[1]
            if not is_open:
                trade["extra"] = True

        # Выкинуть неторговые интервалы
        trades = list(filter(lambda i: not i.get("extra"), trades))

        # Прибавляю N секунд к Quotes, чтобы они запаздывали относительно Trades.
        # Это эмулирует задержку при размещении ордера.
        for quote in quotes:
            quote["timestamp"] += 10_000

        # Combine data and sort by time
        data = sorted(quotes + trades, key=lambda x: x["timestamp"])

        return data

    def data_stream(self, on_event):
        """
        Изображаю события, приходящие с биржи.
        """
        data = []
        for symbol in self.symbols:
            data += self.load_tick_data(symbol, self.dt_from)

        data = sorted(data, key=lambda x: x["timestamp"])

        prev_dt = None
        for event in data:
            symbol = event.get("symbolId")

            if not symbol or "timestamp" not in event:
                continue

            dt = interval_dt(event)

            # Используется для наполнения стратегии историческими данными
            if dt < self.dt_start:
                if "price" in event:
                    on_event("trade_before_start", dt, symbol, parse_quote(event))
                continue

            # Аналитика перед открытием нового интервала
            if prev_dt and dt.day != prev_dt.day:
                norm_dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                on_event("before_interval", norm_dt, symbol)
            prev_dt = dt

            # События с биржи
            if "price" in event:
                on_event("trade", dt, symbol, parse_quote(event))

            if "ask" in event and "bid" in event:
                ask = list(map(parse_quote, event["ask"]))
                bid = list(map(parse_quote, event["bid"]))
                self.quotes[symbol] = {"ask": ask, "bid": bid, "dt": dt}
                on_event("quote", dt, symbol, {"ask": ask, "bid": bid})

            # Любое событие биржи
            on_event("after_event", dt, symbol)

    def start_listen(self, on_event, loop=None):
        """
        В данном случае можно синхронно прогнать все данные.
        """
        self.data_stream(on_event)
        loop.stop()

    def trade(self, side: str, amount: Decimal, symbol: str):
        """
        Создать ордер на бирже, скорректировать позицию.
        """
        cprint(f"\nTRADE: {side} {symbol} {amount}", color="red")

        assert amount != 0

        start_amount = amount

        if price := self.get_price(symbol, side):
            self.cash -= self.fee * amount

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

                print(f"PROFIT: {trade_profit}, amnt {partial_close_amount}")
                self.cash += trade_profit

                # Если amount еще остался — открыть позицию
                if amount != 0:
                    self.positions[symbol] = {
                        "amount": amount,
                        "price": price,
                    }
            else:
                # Увеличение позиции в ту же сторону
                total_value = position["amount"] * position["price"] + amount * price
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

    @property
    def net_value(self):
        """
        Суммарное количество бабла депозита: кэш плюс стоимость активов.
        """
        total_value = self.cash
        for symbol, position in self.positions.items():
            if position["amount"] > 0:
                price = self.get_price(symbol, "sell")
                total_value += position["amount"] * (price - position["price"])
                total_value -= self.fee * position["amount"]
            if position["amount"] < 0:
                price = self.get_price(symbol, "buy")
                total_value += position["amount"] * (position["price"] - price)
                total_value -= self.fee * position["amount"]
        return total_value

    def get_positions(self):
        return self.positions
