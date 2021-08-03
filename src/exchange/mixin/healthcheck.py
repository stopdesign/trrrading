from datetime import timedelta, datetime
from time import sleep
from termcolor import cprint


class Healthcheck:
    finished = None
    healthcheck_interval = 30

    def healthcheck_loop(self):
        interval = timedelta(seconds=self.healthcheck_interval)
        prev_dt = datetime.utcnow()
        while not self.finished:
            if datetime.utcnow() - prev_dt > interval:
                self.do_healthcheck()
                prev_dt = datetime.utcnow()
            sleep(0.5)  # sleep маленький, чтобы цикл не зависал

    def do_healthcheck(self):
        cprint("do_healthcheck", "white")
