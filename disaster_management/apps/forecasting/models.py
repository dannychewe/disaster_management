from django.db import models
from django.contrib.gis.db import models as gis_models


class ForecastModel(models.Model):
    MODEL_TYPE_CHOICES = [
        ('flood', 'Flood'),
        ('drought', 'Drought'),
        ('resource_shortage', 'Resource Shortage'),
        ('heat_wave', 'Heat Wave'),
    ]

    name = models.CharField(max_length=100)
    model_type = models.CharField(max_length=20, choices=MODEL_TYPE_CHOICES)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    version = models.CharField(max_length=20, blank=True, help_text="Optional version tag (e.g. v1.0, beta)")

    class Meta:
        verbose_name = "Forecast Model"
        verbose_name_plural = "Forecast Models"

    def __str__(self):
        return f"{self.name} ({self.model_type})"


class ForecastResult(models.Model):
    RISK_LEVEL_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    model = models.ForeignKey(ForecastModel, on_delete=models.CASCADE, related_name='results')
    forecast_date = models.DateField(help_text="The date the forecast applies to")
    predicted_at = models.DateTimeField(auto_now_add=True)
    affected_area = gis_models.PolygonField(geography=True, null=True, blank=True)
    area_name = models.CharField(max_length=100, blank=True, help_text="Optional name for the affected area")
    risk_level = models.CharField(max_length=10, choices=RISK_LEVEL_CHOICES)
    confidence = models.FloatField(help_text="Confidence level from 0 (low) to 1 (high)")
    details = models.TextField(blank=True)
    incidents = models.ManyToManyField(
        "incidents.Incident",
        blank=True,
        related_name="risk_zones"
    )

    class Meta:
        verbose_name = "Forecast Result"
        verbose_name_plural = "Forecast Results"
        ordering = ['-forecast_date', '-predicted_at']

    def __str__(self):
        return f"{self.model.name} → {self.area_name or 'Area'} on {self.forecast_date} ({self.risk_level})"
