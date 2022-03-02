import sys
import logging.config

conf = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "color_console": {
            "()": "project.helpers.log_formater.DjangoColorsFormatter",
            "format": "{asctime}.{msecs:03.0f} {levelname:.3}  "
            "{filename:>12.12}:{lineno:04d}  {message}",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "color_console",
        },
        # TODO: добавить file handler
    },
    "loggers": {
        "": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
        "django": {"level": "INFO", "handlers": ["console"], "propagate": False},
        # Set level to DEBUG and enable settings.DEBUG to see all SQL queries
        "django.db.backends": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        # Default runserver request logging
        "django.server": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        # suppress DEBUG noise
        "django.utils.autoreload": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        # suppress DEBUG noise
        "urllib3.connectionpool": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}
LOGGING_CONFIG = None
logging.config.dictConfig(conf)


# # console_template = "%(message)s"
# console_template = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# console_formater = ColoredFormatter(console_template)
#
# file_template = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# file_formater = ColoredFormatter(file_template, color=False)
#
# dt = datetime.now()  # server time
# day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
# ts = (dt - day).total_seconds()
#
# root = logging.getLogger()
# root.setLevel(logging.DEBUG)
#
# # Вывожу всё в stdout
# h = logging.StreamHandler(sys.stdout)
# h.setFormatter(console_formater)
# h.setLevel(logging.INFO)
# root.addHandler(h)
#
# log_file_name = f"main_{day:%Y-%m-%d}_{ts:05.0f}.log"
# path = os.path.dirname(__file__)
# path = os.path.abspath(os.path.join(path, "../../log", log_file_name))
#
# # Копию складывать в файл
# h_file = logging.FileHandler(path)
# h_file.setFormatter(file_formater)
# h_file.setLevel(logging.DEBUG)
# root.addHandler(h_file)
