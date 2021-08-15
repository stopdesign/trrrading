from enum import Enum
from types import DynamicClassAttribute


class Signal(Enum):
    PASS = None
    LONG = "LONG"
    SHORT = "SHORT"
    CLOSE = "CLOSE"

    @DynamicClassAttribute
    def open(self):
        return self.value in [Signal.LONG.value, Signal.SHORT.value]

    @DynamicClassAttribute
    def color(self):
        colors = {
            Signal.LONG.value: "green",
            Signal.SHORT.value: "red",
            Signal.CLOSE.value: "blue",
        }
        return colors.get(self.value)

    @DynamicClassAttribute
    def side(self):
        sides = {
            Signal.LONG.value: "buy",
            Signal.SHORT.value: "sell",
        }
        return sides.get(self.value)

    @DynamicClassAttribute
    def numeric(self):
        sides = {
            Signal.LONG.value: 1,
            Signal.SHORT.value: -1,
        }
        return sides.get(self.value, 0)
