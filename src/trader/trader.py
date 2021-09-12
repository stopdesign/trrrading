import math
import logging
import pandas as pd
from typing import List
from datetime import datetime
from decimal import Decimal
from termcolor import colored
from exchange import BaseExchange, all_exchanges
from stats import AccountStats, TradeStats
from strategy import Signal
from trader import Advisor
from trader.tg_bot import TelegramBotMixin

log = logging.getLogger("trader")


class Trader(TelegramBotMixin):
    exchange: BaseExchange = None

    def __init__(self, broker_conf, instruments, base_dir):
        txt = f"Init trader at {datetime.utcnow().replace(microsecond=0)} UTC"
        log.info(colored(txt, "white"))

        self.base_dir = base_dir

        self.target_margin = broker_conf.get("target_margin")
        self.can_short = broker_conf.get("short", True)
        self.resample_rule = broker_conf.get("resample_rule", None)

        self.instruments = instruments
        self.advisors = []

        for symbol, config in instruments.items():
            for advisor_config in config["advisors"]:
                self.advisors.append(Advisor(symbol, **advisor_config))

        exchange_class = all_exchanges[broker_conf.get("driver")]

        if exchange_class.backtest:
            dt = broker_conf.get("dt_start")
            self.dt_start = datetime(dt.year, dt.month, dt.day)
            self.dt_end = broker_conf.get("dt_end")
        else:
            self.dt_start = datetime.utcnow().replace(second=0, microsecond=0)
            self.dt_end = None

        self.exchange = exchange_class(
            instruments,
            dt_start=self.dt_start,
            dt_end=self.dt_end,
            on_event=self.on_event,
        )

        self.account_stats = AccountStats(self, self.exchange)
        self.trade_stats = TradeStats(self, self.exchange)

    def warm_up(self):
        log.info(colored(f"Historical data from {self.exchange.dt_from}", "white"))
        self.exchange.warm_up()
        self.account_stats.portfolio_info()

    def start(self):
        self.start_tg_bot()

        log.info("Start stream")
        self.account_stats.snapshot()
        self.exchange.start_listen()

        log.info("Stop stream")
        self.account_stats.snapshot()
        self.account_stats.portfolio_info()

        self.stop_tg_bot()

    def stop(self):
        self.exchange.stop_listen()

    def final_info(self):
        """
        Завершение торговли (штатное или из-за ошибки).
        Сохранить все наработанные данные.
        """
        csv_dir = f"{self.base_dir}/../front"
        df = pd.DataFrame()
        for advisor in self.get_advisors():
            rd = advisor.strategy.resampled_data(self.resample_rule, self.dt_start)
            df = df.append(rd)
        df.sort_index().to_csv(f"{csv_dir}/data.csv", float_format="%.2f")
        self.trade_stats.to_csv(f"{csv_dir}/trades.csv")
        self.account_stats.to_csv(f"{csv_dir}/stats.csv")
        if self.exchange.backtest:
            self.account_stats.print_summary()  # RESULTS

    def on_event(self, event, dt, symbol=None, payload=None):
        """
        В стриме биржи возникло новое событие.
        """
        if dt >= self.dt_start and not self.exchange.backtest:
            log.debug(f"EVENT {event} {symbol} {payload}")

        if event == "bar":
            for advisor in self.get_advisors(symbol):
                advisor.on_bar(dt, payload)

        if event == "trade" and dt < self.dt_start:
            for advisor in self.get_advisors(symbol):
                advisor.test_price(dt, payload.price)

        if event == "trade" and dt >= self.dt_start:
            self.on_trade(dt, symbol, payload.price)

        if event == "quote":
            self.exchange.add_quote(dt, symbol, payload)

        if event in ["hour", "day", "after_trade"]:
            if dt >= self.dt_start:
                self.account_stats.snapshot()

        if event in ["minute"]:
            pass

        if event == "after_trade":
            self.trade_stats.on_trade_done(dt, symbol, payload)
            self.account_stats.on_trade_done(symbol, payload)
            # self.trade_stats.log_trade_result(symbol, payload)
            if not self.exchange.backtest:
                self.account_stats.portfolio_info()

        return True

    def get_advisors(self, symbol=None) -> List[Advisor]:
        """
        Все советники для данного инструмента.
        """
        return [a for a in self.advisors if not symbol or a.instrument == symbol]

    def get_current_position(self, instrument):
        """
        Сколько сейчас в портфолио есть этой штуки.
        """
        positions = self.exchange.get_positions()
        return positions.get(instrument, BaseExchange.empty_position)["amount"]

    def get_advised_position(self, instrument):
        """
        Сколько сейчас в портфолио должно быть этой штуки.
        """
        state = 0
        for advisor in self.get_advisors(instrument):
            if not advisor.state:
                log.warning(f"NO STATE: {advisor}")
                return None
            state += advisor.state.numeric / len(self.advisors)

        # Шорт должен быть разрешен на уровне бота и инструмента
        instrument_config = self.instruments.get(instrument, {})
        if not (self.can_short and instrument_config.get("short")):
            state = max(0, state)

        try:
            return self.state_to_position(instrument, state)
        except TypeError:
            return None

    def state_to_position(self, instrument, state):
        """
        Какому количеству акций соответствует данный state.
        Учесть разный margin для шорта и лонга.
        При state 1 позиция должна давать target margin.
        """
        margin = self.exchange.get_margin_level(state < 0)
        price = self.exchange.get_price(instrument, "mid")
        return int(math.floor(self.target_margin * state / margin / price))

    def on_trade(self, dt: datetime, symbol, sig_price, volume=None):  # noqa
        """
        Тут торговля, если стратегия дала сигнал.
        """
        if not self.exchange.backtest:
            log.debug(f"ON_TRADE {dt} {symbol} {sig_price}")

        # Протестировать новую цену (не добавляя в историю).
        # Получить сигналы во все стороны.
        buy_signals, sell_signals = self.get_signals(symbol, dt, sig_price)

        # Пересчитать дискретные сигналы в количество акций
        # FIXME: Считает оно неправильно, потому что закрытие
        # FIXME: и открытие нужно считать по разным ценам.
        # FIXME: Или даже менять систему подсчета margin.
        # FIXME: Проблему видно при продаже после сильного роста.
        can_buy = self.state_to_position(symbol, buy_signals)
        can_sell = self.state_to_position(symbol, sell_signals)

        # Это всё должно быть после тестирования новой цены в get_signals,
        # т.к. используется advisor.state, который должен быть посчитан.
        cp = self.get_current_position(symbol)
        ap = self.get_advised_position(symbol)
        diff = ap - cp

        # Если ничего не нужно делать
        if not (diff and (can_buy or can_sell)):
            if not self.exchange.backtest:
                log.debug(f"SKIP: diff: {diff}, buy: {can_buy}, sell: {can_sell}")
            return

        # Посчитать объем ордера, который нужно выставить для изменения позиции
        # из имеющейся в рекомендуемую. Скорректировать по возможностям из сигналов.
        amount, side = 0, None
        if diff > 0:
            amount, side = min(abs(diff), abs(can_buy)), "buy"
        if diff < 0:
            amount, side = -min(abs(diff), abs(can_sell)), "sell"

        # Рыночная цена по текущему стакану
        price = self.exchange.get_price(symbol, side)

        # Предлагаемое изменение позиции должно быть больше минимального
        if abs(amount) < self.get_min_tradable_amount(price):
            amount, side = 0, None

        # Лог того, что собираемся делать
        # TODO: записать параметры в TradeStats в виде шаблона сделки,
        # TODO: передать это в self.exchange.trade (uid или сам объект),
        # TODO: оттуда уже выводить лог pre-trade и post-trade
        self.trade_stats.log_trade(
            dt, symbol, sig_price, price, cp, ap, amount, can_sell, can_buy,
            self.exchange.net_value
        )

        # Если есть все параметры — запустить сделку
        if price and amount:
            self.exchange.trade(side, abs(amount), symbol, dt, sig_price)

    def get_min_tradable_amount(self, price):
        """
        Минимальное количество акций, которое стоит покупать/продавать.
        """
        min_tradable_amount = math.floor(Decimal(100) / Decimal(price))
        min_tradable_amount = max(1, min_tradable_amount)
        return min_tradable_amount

    def get_signals(self, instrument, dt, price):
        """
        Сумма сигналов в каждом направлении.
        """
        total_buy, total_sell = 0, 0
        all_adv_len = len(self.advisors)

        for advisor in self.get_advisors(instrument):
            if advisor.state is None:
                data_len = len(advisor.strategy.data)
                raise Exception(f"Empty state: {advisor}, len: {data_len}")

            old_state = advisor.state.numeric
            signal = advisor.test_price(dt, price)
            state_diff = signal.numeric - old_state

            if signal == Signal.PASS:
                continue

            if state_diff > 0:
                total_buy += abs(state_diff / all_adv_len)

            if state_diff < 0:
                total_sell += abs(state_diff / all_adv_len)

        return total_buy, total_sell
