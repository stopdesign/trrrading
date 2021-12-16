import asyncio
import logging
import nest_asyncio
import pandas as pd
import ib_insync as ib
import pandas_market_calendars as mcal
from datetime import datetime, timedelta
from decimal import Decimal
from termcolor import cprint, colored
from notifications.alert import send_telegram
from exchange.utils.nyse_cal import trading_session, time_to_next_session
from storage.ib import load_many
from exchange import BaseExchange
from exchange.mixin import Healthcheck, AccountEvents
from data_types import BidAsk, Trade, Bar, Margin, Fee
from ib_insync.ticker import TickerUpdateEvent  # noqa
from tortoise import Tortoise

log = logging.getLogger("broker")


# https://interactivebrokers.github.io/tws-api/tick_types.html
TRADE_TYPES = TickerUpdateEvent().trades()._tickTypes  # noqa
BID_TYPES = TickerUpdateEvent().bids()._tickTypes  # noqa
ASK_TYPES = TickerUpdateEvent().asks()._tickTypes  # noqa

BID_ASK_COLUMNS_MAP = {
    "open": "av_bid",
    "high": "max_ask",
    "low": "min_bid",
    "close": "av_ask",
}


async def init_db():
    await Tortoise.init(
        config={
            "connections": {
                "default": {
                    "engine": "tortoise.backends.asyncpg",
                    "credentials": {
                        "database": "bot",
                        "host": "127.0.0.1",
                        "port": 5432,
                        "user": "postgres",
                        "password": "",
                        "minsize": 1,
                        "maxsize": 1,
                    }
                }
            },
            "apps": {
                "models": {
                    "models": ["models"],
                }
            },
        },
    )


class IBFakeExchange(BaseExchange, Healthcheck, AccountEvents):
    healthcheck_interval = 60
    rel_price_cap = 0.005  # на столько limit price будет хуже mid_price
    price_precision = Decimal("0.01")

    margin = Margin(long=0.25, short=0.3)
    fee = Fee(fixed_price=1)

    def __init__(self, instruments: dict, **kwargs):
        super().__init__(instruments, **kwargs)

        self.contracts = []
        self.loop = asyncio.get_event_loop()
        nest_asyncio.apply(self.loop)

        self.ib = ib.IB()
        self.ib_account = None
        self.positions_pnl = {}

        self.trade_exec_data = {}

        # Подписаться на события шлюза IB
        self.ib.connectedEvent += self.on_connect
        self.ib.disconnectedEvent += self.on_disconnect
        self.ib.pendingTickersEvent += self.market_stream_event
        self.ib.errorEvent += self.on_ib_error
        self.ib.accountValueEvent += self.on_ib_value_event
        self.ib.pnlSingleEvent += self.on_ib_pnl_single_event
        self.ib.positionEvent += self.on_ib_position_event
        self.ib.updatePortfolioEvent += self.on_ib_update_portfolio
        self.ib.timeoutEvent += lambda *args: log.error(f"Timeout: {args}")

        # self.ib.commissionReportEvent += lambda t, f, r: log.info(colored(
        #     f"FEE: {t.contract.symbol} #{f.execution.orderId} - {f.time} - "
        #     f"comm: {r.commission} — amnt: {int(f.execution.shares)}",
        #     "red")
        # )

        # self.ib.positionEvent += self.on_ib_event('updateEvent')
        # self.ib.updatePortfolioEvent += self.on_ib_event('updateEvent')

        # self.ib.updateEvent += self.on_ib_event('updateEvent')
        # self.ib.barUpdateEvent += self.on_ib_event('barUpdateEvent')
        self.ib.newOrderEvent += self.on_ib_event('newOrderEvent')
        self.ib.orderModifyEvent += self.on_ib_event('orderModifyEvent')
        self.ib.cancelOrderEvent += self.on_ib_event('cancelOrderEvent')
        # self.ib.openOrderEvent += self.on_ib_event('openOrderEvent')
        self.ib.orderStatusEvent += self.on_ib_order_status_event
        self.ib.execDetailsEvent += self.on_ib_event('execDetailsEvent')
        # self.ib.commissionReportEvent += self.on_ib_event('commissionReportEvent')

        self.ib_params = {
            "host": "127.0.0.1",
            "port": 4001,
            # "port": 7497,
            "clientId": 0,
            "timeout": 10,
        }
        # При clientId > 0 positionEvent приходят только для позиций бота

        self._real_margin = 0
        self._net_value = 0
        self._net_value_dt = datetime(1900, 1, 1)

        self.quotes = {}
        dt_from = kwargs.get("dt_from", self.dt_start - timedelta(days=20))
        self.dt_from = dt_from.replace(hour=0, minute=0, second=0)
        # self.cash_initial = kwargs.get("cash", Decimal("10000"))
        self.cash_initial = self._net_value
        self.cash = self.cash_initial
        self.all_data = pd.DataFrame()
        self.dt_last = None
        self.finished = False

        self._order_lock = {}

    async def on_ib_value_event(self, event):
        if event.tag == "MaintMarginReq":
            self._real_margin = Decimal(event.value)
        if event.tag == "NetLiquidation":
            self._net_value = Decimal(event.value)
            dt = datetime.utcnow().replace(microsecond=0)
            if dt != self._net_value_dt:
                txt = f"{dt}, Net value: {self._net_value}, Margin: {self._real_margin}"
                log.info(colored(txt, "blue"))
            self._net_value_dt = dt

    async def on_ib_pnl_single_event(self, pnl_single):
        """
        Пришел PnL для позиции.
        """
        self.positions_pnl[pnl_single.conId] = pnl_single.dailyPnL

    def on_connect(self):
        log.warning(colored(f"ON_CONNECT", "green"))
        send_telegram("Connected")

    def on_disconnect(self):
        log.warning(colored(f"ON_DISCONNECT", "red"))
        send_telegram("Disconnected")
        # если произошел незапланированный дисконнект — разметить переконнект
        if not self.finished:
            for contract in self.contracts:
                if contract.mkt_ticker:
                    log.warning(f"Failed MKT: {contract.symbol}")
                    contract.mkt_ticker = None
                if contract.bars is not None:
                    log.warning(f"Failed BAR: {contract.symbol}")
                    contract.bars = None
                if contract.pnl_data is not None:
                    log.warning(f"Failed PnL: {contract.symbol}")
                    contract.pnl_data = None

    async def on_ib_error(self, req_id, error_code, error_string, contract):
        if req_id and req_id < 0 and "connection is OK" not in error_string:
            log.error(f"ON_ERROR: {req_id} {error_code} {error_string} {contract}")

        # Отвалилась market data, MKT
        # No market data during competing live session.
        if error_code == 10197:
            for contract in self.contracts:
                log.warning(f"Failed MKT: {contract.symbol}")
                contract.mkt_ticker = None

        # Отвалилась подписка на BAR
        # 10182: Failed to request live updates (disconnected).
        # 162: Trading TWS session is connected from a different IP
        if error_code in [10182, 162]:
            n = 10
            while n > 0:
                n -= 1
                for contract in self.contracts:
                    if contract.bars is not None and contract.bars.reqId == req_id:
                        log.warning(f"Failed BAR: {contract.symbol}")
                        contract.bars = None
                        n = 0
                        break
                await asyncio.sleep(0.5)

    def do_healthcheck(self):
        if self.finished:
            return
        dt = datetime.utcnow().replace(microsecond=0)

        if trading_session(dt) != "main":
            return

        # Возраст Net Value
        if dt - self._net_value_dt > timedelta(minutes=5):
            log.error(
                colored(
                    f"HEALTH: old net_value: "
                    f"{self._net_value_dt}, {self._net_value}",
                    color="red",
                    attrs=["reverse"],
                )
            )

        for contract in self.contracts:
            if contract.last_bar:
                bar_age = datetime.utcnow() - contract.last_bar
                if bar_age > timedelta(minutes=3):
                    log.error(
                        colored(
                            f"HEALTH: old bar {contract.symbol}, {bar_age}",
                            color="red",
                            attrs=["reverse"],
                        )
                    )
            if contract.last_mkt:
                mkt_age = datetime.utcnow() - contract.last_mkt
                log.warning(f"mkt_age: {mkt_age}")

    def contract_symbol(self, contract):
        ex = contract.primaryExchange or contract.exchange
        return f"{contract.symbol}.{ex}"

    def load_historical_data(self):
        df = load_many(self.symbols, ["TRADES", "BIDASK"], start=self.dt_from.date())
        # BIDASK должен приходить раньше TRADES для этого интервала
        return df.sort_values(["date", "ticker", "data_type"])

    def load_current_data(self, contract, data_type):

        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="3 D",
            barSizeSetting="1 min",
            whatToShow=data_type.replace("BIDASK", "BID_ASK"),
            useRTH=False,
            formatDate=2,
            timeout=30,
        )

        # Если после последнего бара прошло больше 100 секунд, то считаем его закрытым.
        # Это происходит при запросе данных за пределами торговой сессии.
        # В других случаях последний бар отрезается.
        last_bar_dt = bars[-1].date.replace(tzinfo=None)
        dt = datetime.utcnow().replace(microsecond=0)
        if dt - last_bar_dt < timedelta(seconds=100):
            bars = bars[:-1]

        df = ib.util.df(bars)
        df["date"] = df["date"].dt.tz_localize(None)
        df = df.set_index("date")

        # # Убрать нулевые объемы
        # df = df.loc[df.volume != 0]

        # РАЗМЕТИТЬ RTH
        start = datetime.utcnow() - timedelta(days=300)
        end = datetime.utcnow() + timedelta(days=1)
        cal_exchange = contract.primaryExchange or contract.exchange
        cal_exchange = cal_exchange.replace("ARCA", "NYSE")
        cal_exchange = cal_exchange.replace("NYMEX", "CMES")
        cal_exchange = cal_exchange.replace("GLOBEX", "CMES")
        cal_exchange = cal_exchange.replace("ECBOT", "CMES")

        cal = mcal.get_calendar(cal_exchange).schedule(start, end)
        by_days = {}
        for day, t in sorted(cal.T.to_dict("list").items()):
            t0 = t[0].to_pydatetime()
            t1 = t[1].to_pydatetime()
            by_days[day.date()] = [t0.replace(tzinfo=None), t1.replace(tzinfo=None)]

        def is_main_session(dt):
            t0, t1 = by_days.get(dt.date(), (None, None))
            return str(int(bool(t0 and t1 and t0 <= dt < t1)))

        df["rth"] = df.index.map(is_main_session)

        # В режиме BID_ASK данные имеют другой смысл. Переименовать.
        if data_type == "BIDASK":
            df.rename(columns=BID_ASK_COLUMNS_MAP, inplace=True)
            df = df.resample("1T").pad()

        if data_type == "TRADES":
            df1 = df.resample("1T").pad()

            df1["volume"] = df["volume"]
            df1["volume"].fillna("0", inplace=True)

            df1["barCount"] = df["barCount"]
            df1["barCount"].fillna("0", inplace=True)

            cols = ["open", "high", "low", "average"]
            df1.loc[df1["volume"] == "0", cols] = df1["close"]

            df1 = df1[(df1["barCount"] != "0") | (df1["rth"] == "1")]
            df = df1

        df["ticker"] = self.contract_symbol(contract)
        df["data_type"] = data_type

        return df

    def warm_up(self):
        """
        Прогнать события по историческим данным.
        """

        # Инициализировать IB-контракты для всех инструментов
        contracts = []
        for symbol in self.symbols:
            sym, pe = symbol.split(".")
            if pe in ["GLOBEX", "NYMEX", "ECBOT"]:
                contract = ib.ContFuture(sym, exchange=pe)
            else:
                contract = ib.Stock(sym, "SMART", "USD", primaryExchange=pe)
            contract.bars = None
            contract.mkt_ticker = None
            contract.pnl_data = None
            contract.last_bar = None
            contract.last_mkt = None
            contracts.append(contract)
        self.contracts = contracts

        # Загрузить исторические данные из файлов
        self.all_data = self.load_historical_data()

        log.info(colored("Real-time data", "white"))
        current_data = []
        try:
            self.ib.connect(**self.ib_params)
            self.ib.qualifyContracts(*self.contracts)  # для загрузки conId
            for contract in self.contracts:
                symbol = self.contract_symbol(contract)
                for data_type in ["TRADES", "BIDASK"]:
                    query = f"ticker == '{symbol}' & data_type == '{data_type}'"
                    tail_df = self.all_data.query(query)
                    last_dt = tail_df.tail(1).index.item().to_pydatetime()
                    df = self.load_current_data(contract, data_type)
                    df = df[df.index > last_dt]
                    current_data.append(df)
        finally:
            self.ib.disconnect()

        current_data.append(self.all_data)
        self.all_data = pd.concat(current_data)
        self.all_data = self.all_data.sort_values(["date", "ticker", "data_type"])

        # Прогнать события по историческим данным
        stream = self.all_data.loc[self.dt_from: self.dt_start]
        for row in stream.itertuples():
            self.historical_stream_event(row)

        # Вычислить последний исторический бар для данного контракта
        for contract in self.contracts:
            symbol = self.contract_symbol(contract)
            query = f"ticker == '{symbol}' & data_type == 'TRADES'"
            last_dt = stream.query(query).tail(1).index.item().to_pydatetime()
            contract.last_bar = last_dt
            txt = f"{symbol:<10} last bar: {contract.last_bar}"
            log.info(colored(txt, color="white"))

        # TODO: вынести отсюда куда-нибудь еще
        # Для каждого символа последние данные
        # о цене должны быть не старше 5 минут
        now = datetime.utcnow().replace(microsecond=0)
        for symbol in self.symbols:
            quote_dt = self.quotes.get(symbol, {}).get("dt")
            if not quote_dt or now - quote_dt > timedelta(minutes=5):
                txt = f"{symbol} outdated quotes: {quote_dt}"
                log.error(colored(txt, color="red", attrs=["reverse"]))

    def start_listen(self):
        # Healthcheck в отдельном потоке
        task = asyncio.to_thread(self.healthcheck_loop)
        asyncio.gather(task, return_exceptions=True)

        # Открыть соединение с базой
        self.loop.run_until_complete(init_db())

        # Поддерживать соединение и подписки на данные
        self.loop.create_task(self.connection_keeper())

        # Интервальные события
        self.loop.create_task(self.metronom())

        self.loop.run_forever()

    def stop_listen(self):
        self.finished = True

        # Отменить все активные ордеры
        if self.ib.isConnected():
            self.ib.reqGlobalCancel()

        try:
            self.ib.sleep(0.5)
        except KeyboardInterrupt:
            pass

        if self.ib.isConnected():
            self.ib.disconnect()

        # Закрыть соединение с базой
        self.loop.run_until_complete(Tortoise.close_connections())

        self.loop.stop()

    async def connection_keeper(self):
        """
        Старается обеспечить постоянное соединение.
        """
        while not self.finished:
            dt = datetime.utcnow().replace(microsecond=0)

            # FIXME: сделать нормальную поддержку настроек про время
            # Возможно, нужно всегда держать соединение, т.к. всегда будут
            # какие-то активы для торговли. Или выключать на выходные.
            # Или настраивать в конфиге брокера.
            # time_to_next = time_to_next_session(dt, main=True)
            # wake_up_in_advance = 300
            # if time_to_next > timedelta(seconds=wake_up_in_advance):
            #     txt = f"Next trading session in {time_to_next}, sleep"
            #     log.warning(colored(txt, color="red", attrs=["reverse"]))
            #     await asyncio.sleep(time_to_next.total_seconds() - wake_up_in_advance)
            #     continue

            if not self.ib.isConnected():
                try:
                    log.info("Reconnect")
                    await self.ib.connectAsync(**self.ib_params)
                    # await self.ib.qualifyContractsAsync(*self.contracts)
                    self.ib_account = self.ib.managedAccounts()[0]
                except asyncio.exceptions.TimeoutError:
                    log.error("Reconnect TimeoutError")
                except ConnectionRefusedError:
                    log.error("Reconnect ConnectionRefusedError")
            if self.ib.isConnected():
                try:
                    await self.ib_resubscribe()
                except Exception as e:
                    log.error(f"Resubscribe Uknown Error: {e}")

            await asyncio.sleep(5)

    def create_on_bar_handler(self, contract):
        async def func(a, b):
            if a is not None and b is not None:
                return await self.on_bar_update(a, b, contract)
            else:
                log.error(colored(f"no a {a} or b {b}", "red"))
                return

        return func

    async def ib_resubscribe(self):
        """
        Подписка на обновления по контрактам.
        """
        for contract in self.contracts:
            assert contract.conId, f"no conId, {contract}"
            assert contract.exchange, f"no exchange, {contract}"

        for contract in self.contracts:
            if contract.bars is not None and contract.last_bar:
                dt = datetime.utcnow()
                if trading_session(dt) != "main":
                    # Не проверять непрерывность данных вне основной сессии.
                    continue
                bar_age = dt - contract.last_bar
                if bar_age > timedelta(minutes=3):
                    log.warning(colored(f"Cancel BAR (old): {contract.symbol}", "red"))
                    self.ib.cancelHistoricalData(contract.bars)
                    contract.bars = None
                await asyncio.sleep(0)

        for contract in self.contracts:
            if contract.bars is None:
                log.info(colored(f"Subscribe BAR: {contract.symbol}", "blue"))
                # Подписка на интервальные данные.
                # С настройкой "2 D" ответ никогда не должен быть пустым
                contract.bars = self.ib.reqHistoricalData(
                    contract,
                    endDateTime="",
                    # Достаточно, чтобы заполнить пробел между
                    # историческими данными и real-time данными.
                    durationStr="2 D",  # два торговых дня, даже после выходных
                    barSizeSetting="1 min",
                    whatToShow="TRADES",
                    useRTH=False,
                    formatDate=2,
                    keepUpToDate=True,
                )
                contract.bars.updateEvent += self.create_on_bar_handler(contract)
                await self.on_bar_update(contract.bars, False, contract)

        await asyncio.sleep(1)

        for contract in self.contracts:
            # Тиковые данные
            if not contract.mkt_ticker:
                log.info(colored(f"Subscribe MKT: {contract.symbol}", "blue"))
                contract.mkt_ticker = self.ib.reqMktData(contract)
                await asyncio.sleep(0.1)
            # P&L данные
            if not contract.pnl_data:
                log.info(colored(f"Subscribe PnL: {contract.symbol}", "blue"))
                self.ib.reqPnLSingle(self.ib_account, "", contract.conId)
                contract.pnl_data = True
                await asyncio.sleep(0.1)
            await asyncio.sleep(0)

    def historical_stream_event(self, row):
        dt = row.Index.to_pydatetime()
        symbol = row.ticker

        # TODO: поставить RTH у payload

        if row.data_type == "BIDASK":
            payload = BidAsk(bid=row.av_bid, ask=row.av_ask)
            self.on_event("quote", dt, symbol, payload)

        if row.data_type == "TRADES":
            for price in [row.open, row.high, row.low, row.close]:
                payload = Trade(price=price, volume=row.volume)
                self.on_event("trade", dt, symbol, payload)
            self.on_event("bar", dt, symbol, row)

    async def market_stream_event(self, tickers):
        # Обработать quotes
        for ticker in tickers:
            symbol = self.contract_symbol(ticker.contract)
            dt = ticker.time.replace(microsecond=0, tzinfo=None)
            ask = ticker.ask if ticker.ask > 0 else None
            bid = ticker.bid if ticker.bid > 0 else None
            if ask or bid:
                payload = BidAsk(bid=bid, ask=ask)
                try:
                    self.on_event("quote", dt, symbol, payload)
                except Exception as e:
                    log.error(f"Exception [on_event quote]: {e}")
            await asyncio.sleep(0)

        # Обработать trades
        for ticker in tickers:
            symbol = self.contract_symbol(ticker.contract)
            dt = ticker.time.replace(microsecond=0, tzinfo=None)
            for tick in ticker.ticks:
                if tick.tickType in TRADE_TYPES and tick.price > 0:
                    payload = Trade(price=tick.price, volume=tick.size)
                    try:
                        self.on_event("trade", dt, symbol, payload)
                    except Exception as e:
                        log.error(f"Exception [on_event trade]: {e}")
                        log.exception(e)
                await asyncio.sleep(0)
            await asyncio.sleep(0)

        # Лучше брать из ticker, но пока пусть так
        dt = datetime.utcnow().replace(microsecond=0)
        self.dt_last = dt

    async def metronom(self):
        """
        Запускает регулярные задачи.
        """
        prev_dt = datetime(1900, 1, 1)
        while not self.finished:
            dt = datetime.utcnow().replace(microsecond=0)
            if dt.minute != prev_dt.minute:
                self.on_event("minute", dt)
            self.last_event["metronom"] = datetime.utcnow()
            await asyncio.sleep(0.1)
            prev_dt = dt

    async def on_bar_update(self, bars, _, contract):
        """
        После появления нового бара отправить событие.
        """
        symbol = self.contract_symbol(contract)
        # Посмотреть, какой бар был последним, и добавить все новые бары
        for bar in bars[-1000:-1]:  # последние 1000, кроме самого последнего
            bar_dt = bar.date.replace(tzinfo=None)
            if not contract.last_bar or bar_dt > contract.last_bar:
                payload = Bar.from_bar_data(bar, symbol)
                self.on_event("bar", bar_dt, symbol, payload)
                contract.last_bar = bar_dt
                await asyncio.sleep(0)

    def trade(self, side, amount, symbol, dt, sig_price):
        """
        Открыть позицию/ордер на бирже.
        """
        contract = None
        for con in self.contracts:
            if symbol and symbol == self.contract_symbol(con):
                contract = con
        if not contract:
            return

        # Добываю цену и делаю запас
        mid_price = self.get_price(symbol, "mid")
        lmt_price = self.get_limit_price(mid_price, side)

        # FIXME: The price does not conform to the price variation for this contract
        lmt_price = round(lmt_price * 4) / 4

        # TODO: Вынести в настройки выбор типа ордера
        # order = ib.LimitOrder(side.upper(), amount, lmt_price, outsideRth=True)

        # Midprice orders are not supported outside of regular trading hours
        # order = ib.Order(
        #     orderType="MIDPRICE",
        #     action=side.upper(),
        #     totalQuantity=amount,
        #     lmtPrice=lmt_price,
        # )

        order = ib.MarketOrder(
            action=side.upper(),
            totalQuantity=amount,
            algoStrategy="Adaptive",
            algoParams=[
                ib.TagValue("adaptivePriority", "Patient"),  # Urgent, Normal, Patient
            ],
            tif="DAY",
        )

        if self._order_lock.get(symbol):
            to_cancel = self._order_lock.get(symbol)

            txt = f"TRADE: #{to_cancel.orderId} cancel {symbol}"
            log.warning(colored(txt, "red", attrs=["reverse"]))

            res = self.ib.cancelOrder(to_cancel)
            log.info(
                f"CANCELED: {res.order.permId}, {res.order.orderId}, "
                f"{res.orderStatus.status}, {res.orderStatus.filled}, "
                f"{res.orderStatus.remaining}"
            )

            try:
                self.ib.waitOnUpdate(timeout=1)
                self.ib.sleep(0.1)
                self._order_lock[symbol] = False
            except KeyboardInterrupt:
                pass

        # Заблокировать работу с этим символом
        self._order_lock[symbol] = order

        # Размещаю ордер
        trade = self.ib.placeOrder(contract, order)

        # Кешируется информация про ордер. Будет сохранена в базу,
        # когда у ордера появится perm_id.
        self.trade_exec_data[trade.orderStatus.orderId] = {
            "dt": dt,
            "sig_price": sig_price,
        }

        txt = f"TRADE #{order.orderId}: {side} {symbol} {amount}"
        log.warning(colored(txt, color="cyan", attrs=["reverse"]))
        send_telegram(txt)

        # Жду исполнения ордера
        prev_state = ""
        last_dt = datetime(1900, 1, 1)
        start_dt = datetime.utcnow().replace(microsecond=0)
        while not trade.isDone():
            dt = datetime.utcnow().replace(microsecond=0)
            cur_state = f"{trade.orderStatus.status} {trade.orderStatus.filled}"
            # Вывожу только изменения или обновления после долгой паузы
            if prev_state != cur_state or (dt - last_dt) > timedelta(seconds=10):
                if dt - last_dt > timedelta(seconds=1):
                    rem = float(amount) - trade.orderStatus.filled
                    sec = (dt - start_dt).total_seconds()
                    log.info(
                        colored(
                            f"TRADE #{order.orderId}: {side} {symbol}  "
                            f"{trade.orderStatus.status:<13} "
                            f"{rem:5.0f} to fill, "
                            f"{sec:0.1f} sec",
                            "white",
                        )
                    )
                    last_dt = dt
            prev_state = cur_state
            try:
                self.ib.waitOnUpdate(timeout=3)
                self.ib.sleep(0.1)
            except KeyboardInterrupt:
                log.error("waitOnUpdate has been interrupted")
                self.stop_listen()
                return

        dt = datetime.utcnow().replace(microsecond=0)
        sec = (dt - start_dt).total_seconds()

        # Жду последний commissionReport
        try:
            self.ib.sleep(1)
        except KeyboardInterrupt:
            pass

        # TODO: всю эту хуйню вынести в TradeStats.log_trade_result
        color = "red"
        fee = None
        amnt_sum = "—"
        if trade.orderStatus.status == "Filled":
            color = "green"
            # commissionReport приходит отдельными событиями,
            # поэтому сумма комиссии может быть неполной.
            if any([f.commissionReport.commission == 0 for f in trade.fills]):
                txt = f"TRADE #{order.orderId}: zero commission report"
                log.warning(colored(txt, "red"))
            com_raw = sum(f.commissionReport.commission for f in trade.fills)
            amnt_sum = sum(int(f.execution.shares) for f in trade.fills)
            fee = f"{com_raw:0.2f}"
        txt = (
            f"TRADE #{order.orderId}: {side} {symbol} {amnt_sum} — "
            f"{trade.orderStatus.status}, "
            f"{trade.orderStatus.avgFillPrice:0.2f}, "
            f"sig: {sig_price:0.2f}, "
            f"mid: {mid_price:0.2f}, "
            f"fee: {fee}, "
            f"time: {sec:0.1f} sec"
        )
        log.warning(colored(txt, color=color, attrs=["reverse"]))

        # Сообщение в телеграм
        # TODO: тоже вынести в TradeStats.что-нибудь
        if trade.orderStatus.status == "Filled":
            side_sym = "▲" if side == "buy" else "▼"
            tele_txt = f"#{order.orderId}: {side_sym} {amnt_sum} {symbol} "
            tele_txt += f"@ {trade.orderStatus.avgFillPrice:0.2f} "
            tele_txt += f"› 30.68, fee: {fee}, {sec:0.0f} sec".replace(" ", " ")
            send_telegram(tele_txt)

        # Событие «успешное завершение сделки»
        payload = {
            "side": side,
            "amount": amount,
            "price": trade.orderStatus.avgFillPrice,
            "profit": None,
            "slippage": 0,  # TODO
            "fee": 0,  # TODO
            "net_value": self.net_value,
        }
        self.on_event("after_trade", dt, symbol, payload)

        # Снимаю блокировку
        self._order_lock[symbol] = False

    def get_limit_price(self, mid_price, side):
        lmt_price = mid_price
        if side == "sell":
            lmt_price -= lmt_price * self.rel_price_cap
        if side == "buy":
            lmt_price += lmt_price * self.rel_price_cap
        lmt_price = float(Decimal(lmt_price).quantize(self.price_precision))
        return lmt_price

    @property
    def net_value(self):
        """
        Суммарное количество бабла депозита: кэш плюс стоимость активов.
        """
        return self._net_value

    @property
    def real_margin(self):
        return self._real_margin

    def get_positions(self):
        positions = {}
        for p in self.ib.portfolio():
            symbol = self.contract_symbol(p.contract)
            positions[symbol] = {
                "daily_pnl": self.positions_pnl.get(p.contract.conId, float("nan")),
                "amount": Decimal(p.position),
                "price": Decimal(str(p.averageCost)),
            }
            # Если такого инструмента раньше не было,
            # то добавить его в отслеживаемые контракты
            has_con = False
            for con in self.contracts:
                if symbol == self.contract_symbol(con):
                    has_con = True
                    break
            if not has_con:
                log.warning(f"Add new contract for '{symbol}'")
                contract = p.contract
                contract.bars = None
                contract.mkt_ticker = None
                contract.pnl_data = None
                contract.last_bar = None
                contract.last_mkt = None
                # Это работает с GLOBEX и NYMEX, но не факт,
                # что будет работать со всем остальным.
                if contract.primaryExchange and not contract.exchange:
                    contract.exchange = contract.primaryExchange
                self.contracts.append(contract)
        self.positions = positions
        return self.positions
