from datetime import datetime


class OrderList(list):
    """
    list с фильтрами.
    """

    status_active = ["New", "Sent", "PreSubmitted", "Submitted"]

    def _cast_type(self, res):
        return type(self)(res)

    def active(self, sid: str | None = None) -> "OrderList":
        return self.filter(sid=sid, status=self.status_active)

    def filter(
        self,
        sid: str | None = None,
        status: list | None = None,
        type: list | None = None,
        before: datetime | None = None,
    ) -> "OrderList":
        res = self

        if sid is not None:
            res = [o for o in res if o.sid == sid]

        if status is not None:
            res = [o for o in res if o.status in status]

        if type is not None:
            res = [o for o in res if o.type in type]

        if before is not None:
            res = [o for o in res if o.created_at < before]

        return self._cast_type(res)
