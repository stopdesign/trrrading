import logging
from datetime import datetime

import pandas as pd
import redis
from django.conf import settings
from django.core.management.base import BaseCommand

from main.views_pnl import PerformanceReport

# Логгер для этого файла
log = logging.getLogger("pnl_w")
log.setLevel(logging.INFO)


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        dt = datetime.utcnow()

        rc = redis.Redis(
            host=settings.TRADIS_HOST,
            port=settings.TRADIS_PORT,
            db=settings.TRADIS_DB,
            decode_responses=True,
        )

        try:
            report = PerformanceReport(rc, account_id=6)
            res = sorted(report.generate().items())

            res_1 = {k: {w: r["pnl"] for w, r in v.items()} for k, v in res}
            print(pd.DataFrame(res_1).T)

        except KeyboardInterrupt:
            print()

        print(f"\nDone in {(datetime.utcnow() - dt).total_seconds():0.3f} s")
