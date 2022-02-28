import sys
import logging.config

conf = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "color_console": {
            "()": "project.helpers.log_formater.DjangoColorsFormatter",
            "format": "{asctime}.{msecs:03.0f}\t{levelname: <8}\t{name}\t "
            "[{filename}:{lineno:d}]\t{message}",
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
    },
    "loggers": {
        "": {"level": "INFO", "handlers": ["console"], "propagate": False},
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
