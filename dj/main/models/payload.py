from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class Payload(models.Model):
    class Type(models.TextChoices):
        CubeSat = "cubesat", "CubeSat"
        MicroSat = "microsat", "MicroSat"
        Deployer = "deployer", "Deployer"
        Other = "other", "Other"

    class ClassIds(models.TextChoices):
        ID_1U = "1U", "1U"
        ID_1_5U = "1.5U", "1.5U"
        ID_2U = "2U", "2U"
        ID_3U = "3U", "3U"
        ID_3UXL = "3UXL", "3UXL"
        ID_6U = "6U", "6U"
        ID_6UXL = "6UXL", "6UXL"
        ID_12U = "12U", "12U"
        ID_12UXL = "12UXL", "12UXL"
        ID_N16_6 = "N16-6", "N16-6"
        ID_N20_7 = "N20-7", "N20-7"
        ID_M36_8 = "M36-8", "M36-8"
        ID_M64_8 = "M64-8", "M64-8"
        ID_S90_9 = "S90-9", "S90-9"
        ID_2132_9 = "2132-9", "2132-9"

    name = models.CharField(max_length=50)

    form_data = models.JSONField(default=dict, encoder=DjangoJSONEncoder, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    customer = models.ForeignKey("Company", null=False, on_delete=models.PROTECT)
    vehicle = models.ForeignKey("Vehicle", null=False, on_delete=models.PROTECT, related_name='payloads')

    dimensions = models.CharField(max_length=50)  # ???
    description = models.TextField(blank=True)

    type = models.CharField(max_length=50, choices=Type.choices)
    sat_amount = models.PositiveIntegerField(default=0)
    class_id = models.CharField(max_length=10, choices=ClassIds.choices, blank=True)

    ear_itar_class = models.CharField(max_length=50, blank=True)

    launch_details = models.TextField(blank=True)

    is_containerized = models.BooleanField(default=False)

    def __str__(self):
        return self.name
