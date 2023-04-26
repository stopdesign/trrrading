from django.db import models


class OrderEvent(models.Model):
    order = models.ForeignKey("Order", on_delete=models.CASCADE)
    status = models.CharField(max_length=50, null=True, blank=True)
    code = models.CharField(max_length=50, null=True, blank=True)
    message = models.TextField(null=True, blank=True)
    time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order} {self.status} {(self.message or '')[:100]}"

    class Meta:
        app_label = "main"
