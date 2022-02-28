from django.db import models


class OrderEvent(models.Model):
    order = models.ForeignKey("Order", on_delete=models.CASCADE)
    status = models.CharField(max_length=50, null=True)
    message = models.CharField(max_length=100, null=True)
    time = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order} {self.status} {self.message}"

    class Meta:
        app_label = "main"
