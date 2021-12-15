from asyncio import sleep
from datetime import timedelta, datetime
from termcolor import cprint
import models
import ib_insync as ib


# self.updateEvent = Event('updateEvent')
# self.barUpdateEvent = Event('barUpdateEvent')
# self.newOrderEvent = Event('newOrderEvent')
# self.orderModifyEvent = Event('orderModifyEvent')
# self.cancelOrderEvent = Event('cancelOrderEvent')
# self.openOrderEvent = Event('openOrderEvent')
# self.orderStatusEvent = Event('orderStatusEvent')
# self.execDetailsEvent = Event('execDetailsEvent')
# self.commissionReportEvent = Event('commissionReportEvent')
# self.updatePortfolioEvent = Event('updatePortfolioEvent')
# self.positionEvent = Event('positionEvent')


class AccountEvents:
    ib: ib.IB
    trade_exec_data: dict

    async def check_trade(self, order, fill):
        ex = fill.execution
        cr = fill.commissionReport
        try:
            trade, new = await models.Trade.get_or_create(
                exec_id=ex.execId,
                defaults=dict(
                    order=order,
                    time=ex.time,
                    amount=ex.shares,
                    price=ex.price,
                    exchange=ex.exchange,
                    commission=cr.commission,
                )
            )
            if not new and cr.commission > 0 and cr.commission > trade.commission:
                trade.commission = cr.commission
                await trade.save()
        except Exception as e:
            cprint(f"EXCEPTION in Trade.get_or_create {e}", "red")

    async def on_ib_order_status_event(self, trade):
        o = trade.order
        os = trade.orderStatus
        contract = trade.contract

        if getattr(contract, "primaryExchange"):
            exchange_symbol = contract.primaryExchange
        else:
            exchange_symbol = contract.exchange

        exchange = await models.Exchange.get_or_none(symbol=exchange_symbol)
        if not exchange:
            cprint(f"Unknown exchange: {exchange_symbol}", "red")
            return

        instrument = await models.Instrument.get_or_none(
            main_exchange=exchange,
            symbol=contract.symbol,
        )
        if not instrument:
            cprint(f"Create instrument: {contract.symbol}.{exchange_symbol}", "red")
            res = await self.ib.reqContractDetailsAsync(contract)
            contract_details = res[0]
            instrument = await models.Instrument.create(
                main_exchange=exchange,
                symbol=contract.symbol,
                sec_type=contract.secType,
                multiplier=(contract.multiplier or 1),
                min_tick=contract_details.minTick,
                description=contract_details.longName,
            )

        if o.permId:
            try:
                order, new = await models.Order.get_or_create(
                    uid=o.permId,
                    defaults=dict(
                        order_id=o.orderId,
                        instrument=instrument,
                        amount=o.totalQuantity,
                        filled=os.filled,
                        action=o.action,
                        type=o.orderType,
                        lmt_price=o.lmtPrice,
                        avg_fill_price=os.avgFillPrice,
                        is_bot=False,
                        status=os.status,
                    )
                )
            except Exception as e:
                cprint(f"EXCEPTION in Order.get_or_create {e}", "red")
                return

            # print("order created", new, o.orderId)
            if new and o.orderId in self.trade_exec_data:
                # print("save sig price", self.trade_exec_data[o.orderId])
                order.sig_price = self.trade_exec_data[o.orderId]["sig_price"]
                await order.save()

            # Сохранить новый статус
            if not new and order.status != os.status:
                oe = models.OrderEvent(order=order, status=os.status)
                await oe.save()
                order.status = os.status
                await order.save()

            # Сохранить/обновить сделки и комиссии
            for f in trade.fills:
                await self.check_trade(order, f)

            # Обновить filled
            if not new and order.filled != os.filled:
                order.filled = os.filled
                await order.save()

            # Обновить avgFillPrice
            if not new and order.avg_fill_price != os.avgFillPrice:
                order.avg_fill_price = os.avgFillPrice
                await order.save()

        for o in await self.ib.reqAllOpenOrdersAsync():
            order = await models.Order.get_or_none(uid=o.permId)
            if order:
                # update
                pass
            else:
                cprint(f"UNKNOWN ORDER: {order}", "red")

    async def on_ib_position_event(self, position):
        """
        Меняется размер позиции.
        Или раз в три минуты по расписанию, вроде бы.
        """
        dt = datetime.utcnow().replace(microsecond=0)
        # cprint(
        #     f"{dt}: on position, "
        #     f"{position.contract.symbol}, "
        #     f"{position.position}, "
        #     f"{position.avgCost} ",
        #     "yellow",
        # )
        #
        # print("on_ib_position_event")
        # await write_trade()

    async def on_ib_update_portfolio(self, item):
        """
        Меняется размер или стоимость позиции в портфолио.
        """
        dt = datetime.utcnow().replace(microsecond=0)
        # cprint(
        #     f"{dt}: on update portfolio, "
        #     f"{item.contract.symbol}, "
        #     f"{item.position}, "
        #     f"{item.marketValue} ",
        #     "yellow",
        # )

    def on_ib_event(self, event_name):

        async def event(*args, **kwargs):
            pass
            # cprint(f"EVENT: {event_name}, args: {args}, kwargs: {kwargs}", "cyan")
            # print()

        return event
