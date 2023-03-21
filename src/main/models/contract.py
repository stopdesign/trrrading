import re
from django.db import models
from calendar import month_abbr


MONTHS = list(month_abbr)


def month_code_to_number(code):
    """
    Some code by ChatGPT.
    """
    code = code.upper()
    month_codes = {
        "F": 1,
        "G": 2,
        "H": 3,
        "J": 4,
        "K": 5,
        "M": 6,
        "N": 7,
        "Q": 8,
        "U": 9,
        "V": 10,
        "X": 11,
        "Z": 12,
    }
    return month_codes[code]


class Contract(models.Model):
    class Type(models.TextChoices):
        fut = "FUT", "Futures"
        stk = "STK", "Equity"
        opt = "OPT", "Options"
        cash = "CASH", "Cash"
        crypto = "CRYPTO", "Crypto"

    sid = models.CharField(max_length=50, default="")
    multiplier = models.DecimalField(default=1, max_digits=10, decimal_places=4)
    min_tick = models.DecimalField(default=0.01, max_digits=8, decimal_places=4)
    sec_type = models.CharField(max_length=50, choices=Type.choices, default=Type.stk)

    def __str__(self):
        return f"{self.sid}"

    @classmethod
    def from_ib(cls, contract, sid):
        multiplier = contract.multiplier or 1
        return cls(
            sid=sid,
            multiplier=multiplier,
            min_tick=0.01,
            sec_type=contract.secType,
        )

    class Meta:
        app_label = "main"
