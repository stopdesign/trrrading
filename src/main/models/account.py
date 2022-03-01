from django.db import models


class Account(models.Model):
    uid = models.CharField(max_length=50, unique=True)
    paper = models.BooleanField(default=False)
    username = models.CharField(max_length=50, default="")

    def __str__(self):
        return self.uid

    class Meta:
        app_label = "main"
