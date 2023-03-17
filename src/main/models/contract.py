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

    # TODO: выбросить всё это, оставить SID.
    # SID должен быть в базе, чтобы можно было по нему искать контракт.
    conid = models.PositiveIntegerField(null=True)
    symbol = models.CharField(max_length=50)
    local_symbol = models.CharField(max_length=50, null=True)
    main_exchange = models.ForeignKey("Exchange", null=False, on_delete=models.PROTECT)

    multiplier = models.DecimalField(default=1, max_digits=10, decimal_places=4)
    min_tick = models.DecimalField(default=0.01, max_digits=8, decimal_places=4)
    sec_type = models.CharField(max_length=50, choices=Type.choices, default=Type.stk)

    def __str__(self):
        return f"{self.local_symbol}.{self.main_exchange.symbol}"

    @property
    def ticker(self):
        # deprecated
        return f"{self.local_symbol}.{self.main_exchange.symbol}"

    @property
    def sid(self):
        sid = f"{self.main_exchange.symbol}_{self.local_symbol}"
        if self.sec_type == self.Type.stk:
            sid = f"{self.main_exchange.symbol}_{self.symbol}"
        if self.sec_type == self.Type.fut:
            sid = f"{self.main_exchange.symbol}_{self.symbol}"
            ls = str(self.local_symbol)
            exp_str = ""
            if " " in ls:
                # ZW MAY 23
                _, m, y = re.compile(r"\s+").sub(" ", ls).split(" ")
                m_str = "%02d" % MONTHS.index(m.title())
                y_str = "%02d" % int(y)
                exp_str = y_str + m_str
            else:
                # MESJ3
                ls = ls.replace(self.symbol, "")
                m = month_code_to_number(ls[0])
                y = int(ls[1])
                # Поддерживаем историю с 2017 года
                if y > 6:
                    y += 10
                else:
                    y += 20
                y_str = "%02d" % int(y)
                m_str = "%02d" % m
                exp_str = y_str + m_str
            if exp_str:
                sid += "_" + exp_str
        return sid

    @classmethod
    def from_ib(cls, contract):
        multiplier = contract.multiplier or 1
        return cls(
            conid=contract.conId,
            symbol=contract.symbol,
            local_symbol=contract.localSymbol,
            main_exchange_id=1,
            multiplier=multiplier,
            min_tick=0.01,
            sec_type=contract.secType,
        )

    class Meta:
        app_label = "main"
