from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from django.core.management.base import BaseCommand

from main.models import Account, Trade

ACCOUNT = "U3034375"
CSV_PATH = f"~/projects/trading/trrrading/tmp/{ACCOUNT}_commission.csv"


class Command(BaseCommand):
    """
    Одноразовый скрипт, который пишет в базу комиссии по сделкам из CSV-отчета.
    Сделки аккаунта матчатся только по времени и количеству, символ не проверяется.
    """

    def main(self, account, commissions_by_dt):
        trades = Trade.objects.order_by("time").filter(account=account)

        for trade in trades:
            if not trade.time:
                continue

            dt = trade.time.astimezone(ZoneInfo("America/New_York"))
            dt = dt.replace(tzinfo=None)

            quantity = trade.amount
            if trade.order.action == "SELL":
                quantity = -trade.amount

            key = f"{dt}_{quantity}"
            if key not in commissions_by_dt:
                dt -= timedelta(seconds=1)
                key = f"{dt}_{quantity}"

            commission = commissions_by_dt.get(key)

            if commission:
                trade.commission = -commission.Commission
                trade.save(update_fields=["commission"])
            else:
                print(trade.pk, trade, commission)

    def handle(self, *args, **kwargs):
        account = Account.objects.get(uid=ACCOUNT)
        print(f"\n{account}\n")

        df = pd.read_csv(CSV_PATH, parse_dates=True)
        df = df[["Symbol", "DateTime", "Quantity", "Commission"]]

        commissions_by_dt = {}
        for row in df.itertuples():
            dt = datetime.fromisoformat(row.DateTime.replace(",", ""))
            key = f"{dt}_{row.Quantity}"
            commissions_by_dt[key] = row

        try:
            self.main(account, commissions_by_dt)
        except KeyboardInterrupt:
            print()
            print("DONE")
