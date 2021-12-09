import os
import re
import sys
import logging
from copy import copy
from datetime import datetime

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[0;%dm"


COLORS = {
    "INFO": BLUE,
    "DEBUG": WHITE,
    "WARNING": YELLOW,
    "ERROR": RED,
    "CRITICAL": MAGENTA,
}


class ColoredFormatter(logging.Formatter):
    uncolor_rx = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def __init__(self, msg, color=True):
        super().__init__(msg, datefmt="%Y-%m-%d %H:%M:%S")
        self.color = color

    @staticmethod
    def msg_args(r):
        return str(r.msg) % r.args if r.args else str(r.msg)

    @staticmethod
    def uncolor(text):
        return ColoredFormatter.uncolor_rx.sub("", text).strip()

    def format(self, rec):
        rec = copy(rec)
        lvl = rec.levelname
        if self.color and lvl in COLORS:
            levelname_color = (
                COLOR_SEQ % (30 + COLORS[lvl]) + lvl + RESET_SEQ
            )
            rec.levelname = levelname_color

        if not self.color:
            rec.getMessage = lambda: self.uncolor(self.msg_args(rec))

        return super().format(rec)


# console_template = "%(message)s"
console_template = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
console_formater = ColoredFormatter(console_template)

file_template = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
file_formater = ColoredFormatter(file_template, color=False)

dt = datetime.now()  # server time
day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
ts = (dt - day).total_seconds()

root = logging.getLogger()
root.setLevel(logging.DEBUG)

# Вывожу всё в stdout
h = logging.StreamHandler(sys.stdout)
h.setFormatter(console_formater)
h.setLevel(logging.INFO)
root.addHandler(h)

log_file_name = f"main_{day:%Y-%m-%d}_{ts:05.0f}.log"
path = os.path.dirname(__file__)
path = os.path.abspath(os.path.join(path, "../../log", log_file_name))

# Копию складывать в файл
h_file = logging.FileHandler(path)
h_file.setFormatter(file_formater)
h_file.setLevel(logging.DEBUG)
root.addHandler(h_file)

# Уровни логов для ib_insync
logging.getLogger("ib_insync.ib").setLevel(logging.WARNING)
logging.getLogger("ib_insync.client").setLevel(logging.WARNING)
logging.getLogger("ib_insync.wrapper").setLevel(logging.WARNING)

logging.getLogger("aiogram").setLevel(logging.INFO)
logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)
