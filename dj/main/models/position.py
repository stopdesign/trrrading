from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class Position(models.Model):
    instrument = models.ForeignKey("Instrument", null=False, on_delete=models.PROTECT)
    amount = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # form_data = models.JSONField(default=dict, encoder=DjangoJSONEncoder, blank=True)

    # dimensions = models.CharField(max_length=50)  # ???
    # description = models.TextField(blank=True)
    #
    # type = models.CharField(max_length=50, choices=Type.choices)
    # sat_amount = models.PositiveIntegerField(default=0)
    # class_id = models.CharField(max_length=10, choices=ClassIds.choices, blank=True)
    #
    # ear_itar_class = models.CharField(max_length=50, blank=True)
    #
    # launch_details = models.TextField(blank=True)
    #
    # is_containerized = models.BooleanField(default=False)

    # def __str__(self):
    #     return self.name
