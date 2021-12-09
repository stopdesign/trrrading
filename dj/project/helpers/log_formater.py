import logging
from django.core.management.color import color_style


class DjangoColorsFormatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        super(DjangoColorsFormatter, self).__init__(style="{", *args, **kwargs)
        self.style = self.configure_style(color_style())

    def configure_style(self, style):
        style.DEBUG = style.HTTP_NOT_MODIFIED
        style.INFO = style.SUCCESS
        style.WARNING = style.WARNING
        style.ERROR = style.ERROR
        style.CRITICAL = style.HTTP_SERVER_ERROR
        return style

    def format(self, record):
        message = super(DjangoColorsFormatter, self).format(record)
        colorizer = getattr(self.style, record.levelname, self.style.HTTP_SUCCESS)

        # Shorter package names
        if ".management.commands." in record.name:
            message = message.replace(str(record.name), str(record.module))

        return colorizer(message)
