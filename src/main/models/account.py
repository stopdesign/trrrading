from django.db import models


class Account(models.Model):
    uid = models.CharField(max_length=50, unique=True)
    paper = models.BooleanField(default=False)
    description = models.CharField(max_length=100)

    def __str__(self):
        return self.uid

    class Meta:
        app_label = "main"
