
class Strategy:
    pass

class TrendIndicator:
    pass

class ChannelIndicator:
    pass


class CoolStrategy(Strategy):

    def on_start(self):

        # Подписка на интервальные данные.
        # Эти подписки приводят к событиям on_bar.
        spy_30m = self.addData("SPY", "30m", rth=True, tick=True)  # что возвращать? что с tick data?

        # это как будто бы встроенный consolidator
        ura_5m = self.addData("URA", "5m", rth=True, handler=self.on_bar)

        # consolidator просто собирает бары, пока не придет бар из следующего интервала.
        # он возвращает один бар, историю нужно отдельно собирать.

        # Может, сделать отдельную подписку на tick data?
        # On Trade - это именно тиковые данные или эмуляция бара тоже?
        # бывает ли эмуляция отдельных сделок бара для реальной торговли? НЕТ.

        # Индикаторы.
        # Им сразу передается датасет, на котором они работают.
        # Там и инструмент, и таймфрейм, и все настройки.
        self.trend = TrendIndicator(spy_30m, length=20, method="SMA")
        self.channel = ChannelIndicator(ura_5m, length=50)

        # Что-то можно поделать с ордерами этой стратегии от других запусков.

    # on_bar один на все подписки? Как различать, откуда это пришло?
    # on_bar вызывается на каждый интервал для каждого инструмента или один раз?
    def on_bar(self, bar):
        """
        Стратегия:
            - если позиции нет, то создать ордеры в обе стороны
            - если позиция есть, то создать ордер в противоположную позицию
            - если ордер есть, подвинуть его stop_price в соответствии с индикатором
            - при исполнении ордера создается противоположный ордер
            
            В каждый момент времени должен быть или ордер в кажду сторону,
            или позиция и ордер в другую сторону.

            Но что-то деактивируется, если тренд не туда.

        Подвинуть цену по новому значению индикатора.
        Update может ничего не менять, если было такое же значение.

        Деактивировать ордер, если другой индикатор показал что-то про тренд.

        """
        # как-то получить актуальный ордер
        # что делать, если есть два ордера?
        order = self.current_order

        # как-то получить позицию по данному инструменту
        position = self.position

        if order and order.direction == "buy":
            order.update(lmt_price=self.channel.up)

        if order and order.direction == "sell":
            order.update(lmt_price=self.channel.dn)

        if not order:
            
            if position >= 0:
                self.stop_order(direction="sell", stop_price=self.channel.dn)

            if position <= 0:
                self.stop_order(direction="buy", stop_price=self.channel.up)


    def on_tick(self, tick):
        """
        В данной стратегии здесь ничего не происходит, но могло бы.
        """
        print(tick)

    def on_order_event(self, order, event):
        """
        Если ордер сработал, открыть ордер в противоположную сторону.
        Если ордер отменился - открыть туда же, наверное. Или нет.
        """
        if order.filled:
            # открыть ордер в обратную сторону
            # Или тот же алгоритм, что в on_bar.
            # Или просто подождать on_bar.
            pass

        if order.canceled:
            self.alert("order canceled")




class Grains(Strategy):
    
    # Order ticket for our stop order, Datetime when stop order was last hit
    stopMarketTicket = None
    
    def Initialize(self):

        # нужно ли это здесь?
        self.SetStartDate(2022, 1, 1)
        self.SetEndDate(2022, 10, 5)
        self.SetCash(100000)

        # Интересно. Можно для разных алгоритмов задать разные модели реальности.
        # self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Cash)

        # подписка на данные
        # как подписаться на интервалы и на тиковые данные?

        # Security - это типа строка, идентификатор инструмента??
        # self.symbol = self.AddData(CustomData, "CustomData", Resolution.Hour).Symbol

        # The AddEquity method returns an Equity
        # <Securities> = self.AddEquity("SPY", Resolution.Minute, rth=True)

        # Фьючерсы
        # self.contract_symbol = Symbol.CreateFuture(Futures.Indices.SP500EMini, Market.CME, datetime(2022,6,17))
        # continuous_future_symbol = Symbol.Create(Futures.Indices.SP500EMini, SecurityType.Future, Market.CME)
        # contract_symbols = self.FutureChainProvider.GetFutureContractList(continuous_future_symbol, self.Time)
        # self.contract_symbol = sorted(contract_symbols, key=lambda symbol: symbol.ID.Date)[0]
        # self.AddFutureContract(self.contract_symbol)



        # Securities - Библиотека всех инструментов (или контрактов)
        # It is a dictionary where the key is a Symbol and the value is a Security

        # self.Securities["SPY"] - хуйня какая-то неудобная.
        # self.Securities["SPY"].Close - что вообще, какого хрена...
        # self.Securities["SPY"].GetLastData() - ёптвоюмать, что за говно11


        # Дальше подгружаются данные портфолио и ...


        # Что-то типа аккаунта. Сумма чего-нибудь по всем позициям.
        # Portfolio - provides information about the whole portfolio state 
        #   holding = self.Portfolio["SPY"]


        # Это какое-то говно со списком ордеров и сделок
        # Transactions
        #
        # order_tickets = self.Transactions.GetOrderTickets()
        # OrderTicket - это натурально ордер, только хуже.
        # limit_price = order_ticket.Get(OrderField.LimitPrice) - ёптвоюмать, какое дно!
        #
        # symbol_open_order_tickets = self.Transactions.GetOpenOrderTickets(symbol)
        # order_id = self.Transactions.LastOrderID
        # order = self.Transactions.GetOrderById(order_id)


        # Настройки индикатора и прогрев.
        self.sma = self.SMA(self.symbol, 20)


    def OnData(self, slice: Slice) -> None:
        """
        The Slice object represents all of the data at a moment of time.
        The self.Time property of your algorithm is always equal to the Time Frontier.

        Вот тут хуйня:
        data = slice[self.symbol] - возвращает TradeBar для Equities или QuoteBar для остального.

        # Это уже лучше:
        trade_bar = slice.Bars[self.symbol]
        quote_bar = slice.QuoteBars[self.symbol]

        # Можно еще вот так. Чем отличается - непонятно.
        bar = data.Bars[self.symbol]

        quantity = self.Portfolio.GetBuyingPower(self.symbol, OrderDirection.Buy)

        Индикаторы. Что с ними делать?

        """
        
        self.Time  # время в данный момент? Зачем?

        if not self.Portfolio.Invested:
            self.MarketOrder("SPY", 10)

            # Сделать stop-market ордер и сохранить указатель на него
            stopPrice = round(0.9 * self.Securities["SPY"].Close, 2)
            self.stopMarketTicket = self.StopMarketOrder("SPY", -10, stopPrice)
        
        else:
            
            #1. Check if the SPY price is higher that highestSPYPrice.
            if self.Securities["SPY"].Close > self.highestSPYPrice:
                
                #2. Save the new high to highestSPYPrice; 
                # then update the stop price to 90% of highestSPYPrice 
                self.highestSPYPrice = self.Securities["SPY"].Close
                updateFields = UpdateOrderFields()
                updateFields.StopPrice = round(self.highestSPYPrice * 0.9, 2)
                self.stopMarketTicket.Update(updateFields)
                
                #3. Print the new stop price with Debug()
                self.Log("SPY: " + str(self.highestSPYPrice) + " Stop: " + str(updateFields.StopPrice))


        # Создание и обновление ордера
        """
        # Create an order 
        quantity = self.Portfolio.GetBuyingPower(self.symbol, OrderDirection.Buy)
        ticket = self.LimitOrder("SPY", quantity, 221.05, False, "New SPY trade")

        # Update the order tag and limit price
        updateSettings = UpdateOrderFields()
        updateSettings.LimitPrice = 222.00
        updateSettings.Tag = "Limit Price Updated for SPY Trade"
        response = ticket.Update(updateSettings)

        # Или вот так.
        response = ticket.UpdateLimitPrice(limitPrice, tag="bla-bla")

        # Check the OrderResponse
        if response.IsSuccess:
            self.Debug("Order updated successfully")
        """


    def OnOrderEvent(self, orderEvent: OrderEvent) -> None:

        # с ордером что-то произошло, но он еще не исполнен
        if orderEvent.Status != OrderStatus.Filled:
            return
        
        # хуйня какая-то, это должно происходить само
        if self.stopMarketTicket is not None and self.stopMarketTicket.OrderId == orderEvent.OrderId: 
            self.stopMarketOrderFillTime = self.Time



