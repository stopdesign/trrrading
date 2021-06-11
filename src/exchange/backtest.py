from datetime import datetime, timedelta
from decimal import Decimal
import pandas_market_calendars as mcal
from termcolor import cprint, colored
from exchange import BaseExchange
from util import interval_dt, load_from_file, parse_quote


class BacktestExchange(BaseExchange):

    def __init__(self, symbols: list, **kwargs):
        super().__init__(symbols)

        self.quotes = {}

        self.dt_start = kwargs.get("dt_start", datetime(2021, 1, 5))
        self.dt_from = self.dt_start - timedelta(days=5)
        self.cash_initial = kwargs.get("cash", Decimal(10_000))
        self.cash = self.cash_initial
        self.fee_rate = Decimal("0.02")
        self.all_data = self.load_data()

    def load_data(self):
        data = []
        for symbol in self.symbols:
            data += self.load_tick_data(symbol, self.dt_from)
        return sorted(data, key=lambda x: x["timestamp"])

    def load_tick_data(self, symbol, dt_from):
        """
        Чтение архивных данных из файлов.
        """
        quotes_file = f"../data/live-{symbol}-quotes-ticks.jsonl"
        trades_file = f"../data/live-{symbol}-trades-ticks.jsonl"
        # quotes_file = ""
        # trades_file = f"../data/live-{symbol}-trades-fake.jsonl"

        cprint(f" Load ticks: {dt_from}, {symbol} ", attrs=["reverse"])

        try:
            quotes = load_from_file(quotes_file, dt_from)
        except FileNotFoundError:
            cprint("No quotes data", "red")
            print()
            quotes = []

        trades = load_from_file(trades_file, dt_from, symbol)

        # Если нет настоящих quotes, то каждый trade используется как quote
        if not quotes:
            spread = self.fee_rate * 1
            for trade in trades:
                price = Decimal(trade["price"])
                quotes.append({
                    "symbolId": symbol,
                    "timestamp": trade["timestamp"],
                    "ask": [{"price": price + spread, "size": 100}],
                    "bid": [{"price": price - spread, "size": 100}],
                })

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

        # Прибавляю N секунд к Quotes, чтобы они запаздывали относительно Trades.
        # Это эмулирует задержку при размещении ордера.
        for quote in quotes:
            quote["timestamp"] += 10_000

        # Combine data and sort by time
        data = sorted(quotes + trades, key=lambda x: x["timestamp"])

        return data

    def process_historical_data(self, on_event):
        """
        Прогнать события по историческим данным.
        Предзаполняются цены и сигналы, торговля не происходит.
        """
        for event in self.all_data:
            symbol = event.get("symbolId")

            if not symbol or "timestamp" not in event:
                continue

            dt = interval_dt(event)

            # Используется для наполнения историческими данными
            if dt < self.dt_start:
                if "ask" in event:
                    ask = list(map(parse_quote, event["ask"]))
                    bid = list(map(parse_quote, event["bid"]))
                    on_event("historical_quote", dt, symbol, {"ask": ask, "bid": bid})
                if "price" in event:
                    on_event("historical_trade", dt, symbol, parse_quote(event))

    def data_stream(self, on_event):
        """
        Изображаю события, приходящие с биржи.
        """
        prev_dt = None
        for event in self.all_data:
            symbol = event.get("symbolId")

            if not symbol or "timestamp" not in event:
                continue

            dt = interval_dt(event)

            # Используется для наполнения историческими данными
            if dt < self.dt_start:
                continue

            # Аналитика перед открытием нового интервала
            if prev_dt and dt.hour != prev_dt.hour:
                norm_dt = dt.replace(minute=0, second=0, microsecond=0)
                on_event("before_interval", norm_dt, symbol)
            prev_dt = dt

            # События с биржи
            if "ask" in event and "bid" in event:
                ask = list(map(parse_quote, event["ask"]))
                bid = list(map(parse_quote, event["bid"]))
                on_event("quote", dt, symbol, {"ask": ask, "bid": bid})

            if "price" in event:
                on_event("trade", dt, symbol, parse_quote(event))

            # Любое событие биржи
            on_event("after_event", dt, symbol)

    def start_listen(self, on_event, loop=None):
        """
        В данном случае можно синхронно прогнать все данные.
        """
        self.data_stream(on_event)
        loop.stop()

    def stop_listen(self, loop=None):
        """
        Позакрывать все позиции.
        """
        for symbol, position in self.positions.items():
            if position["amount"] > 0:
                self.trade("sell", abs(position["amount"]), symbol)
            if position["amount"] < 0:
                self.trade("buy", abs(position["amount"]), symbol)

    def trade(self, side: str, amount: Decimal, symbol: str):
        """
        Создать ордер на бирже, скорректировать позицию.
        """
        if side == "sell":
            color = "red"
        else:
            color = "green"
        cprint(f"TRADE: {side} {symbol} {amount}", color)

        assert amount != 0

        start_amount = amount

        if price := self.get_price(symbol, side):
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
                txt += colored(f" {trade_profit:+0.2f} ", color, attrs=["reverse"])
                txt += colored(f"{rel_profit:+0.2f}% ", color, attrs=["reverse"])
                self.cash += trade_profit
                txt += colored(f" Σ {self.cash:0.0f} ", "white", attrs=["reverse"])
                print(txt)

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

    def get_positions(self):
        return self.positions
