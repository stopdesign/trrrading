import logging.config
import sys

import coloredlogs

try:
    from .settings_local import LOG_DATE_FMT
except:
    LOG_DATE_FMT = "%Y-%m-%d %H:%M:%S"

try:
    from .settings_local import NO_COLOR
except:
    NO_COLOR = False

FMT = "%(asctime).19s • %(levelname).1s • %(name)s %(lineno)d • %(threadName)s • %(message)s"

if NO_COLOR:
    console_formater = "plainlogs"
else:
    console_formater = "coloredlogs"

conf = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "coloredlogs": {
            "()": coloredlogs.ColoredFormatter,
            "fmt": FMT,
            "datefmt": LOG_DATE_FMT,
        },
        "plainlogs": {
            "format": FMT,
            "datefmt": LOG_DATE_FMT,
        },
        "verbose": {
            "format": FMT,
            "datefmt": LOG_DATE_FMT,
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": console_formater,
        },
        'syslog': {
            'level': 'ERROR',
            'class': 'logging.handlers.SysLogHandler',
            'formatter': 'verbose',
            'address': '/dev/log',
        },
        # TODO: добавить file handler
    },
    "loggers": {
        "": {"level": "DEBUG", "handlers": ["console", ], "propagate": False},
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
        # suppress DEBUG noise
        "ibapi": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False,
        },
        # suppress DEBUG noise
        "ibapi.wrapper": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}
LOGGING_CONFIG = None
logging.config.dictConfig(conf)
