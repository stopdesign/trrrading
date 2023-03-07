from talipp.indicators import DonchianChannels as TalippDonchianChannels

from .base import BaseIndicator 


class DonchianChannels(BaseIndicator):

    def __init__(self, length):
        self.data = TalippDonchianChannels(length)
        self.value = {}

    def on_bar(self, bar):

        skip = False

        if not bar.rth:
            skip = True

        if bar.volume == 0:
            skip = True

        # При каких-то условиях добавить данные в индикатор
        if not skip:
            self.data.add_input_value(bar)

        # Значения индикатора возвращаются для дальнейшего использования.
        # Значения добавляются и в те бары, которые не передавались в индикатор.
        self.value = {
            "ub": self.data[-1].ub if self.data else None,
            "lb": self.data[-1].lb if self.data else None,
        }
