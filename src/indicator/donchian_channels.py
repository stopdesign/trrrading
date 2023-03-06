from talipp.indicators import DonchianChannels as TDC

from .base import BaseIndicator 


class DonchianChannels(BaseIndicator):

    def __init__(self, length):
        self.data = TDC(length)

    def on_bar(self, bar):

        skip = False

        if not bar.rth:
            skip = True

        if bar.volume == 0:
            skip = True

        if not skip:
            self.data.add_input_value(bar)

        # if self.don and not skip:
        #     bar.up = self.don[-1].ub
        #     bar.dn = self.don[-1].lb
        # else:
        #     if self.data and bar.rth:
        #         bar.up = self.data[-1].up
        #         bar.dn = self.data[-1].dn
