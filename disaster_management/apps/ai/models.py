from django.db import models

# Create your models here.
# disaster_management/apps/ai/models.py
from django.db import models
from django.utils import timezone
from django.conf import settings

class IncidentAIAnalysis(models.Model):
    incident = models.OneToOneField(
        "incidents.Incident",
        on_delete=models.CASCADE,
        related_name="ai_analysis"
    )
    risk_score = models.FloatField()
    confidence = models.FloatField(default=0.8)
    label = models.CharField(max_length=20)
    drivers = models.JSONField(default=dict, blank=True)
    version = models.CharField(max_length=20, default="v0.1")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"AI Analysis {self.label} ({self.risk_score}) for {self.incident_id}"


class WeatherFeatures(models.Model):
    incident = models.OneToOneField(
        "incidents.Incident",
        on_delete=models.CASCADE,
        related_name="weather_features"
    )
    rain_30d_pct = models.FloatField(default=0.0)
    forecast_7d_risk = models.FloatField(default=0.0)
    wind_7d = models.FloatField(default=0.0)
    computed_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"WeatherFeatures for {self.incident_id}"


class SpatialContext(models.Model):
    incident = models.OneToOneField(
        "incidents.Incident",
        on_delete=models.CASCADE,
        related_name="spatial_context"
    )
    proximity_water = models.FloatField(default=0.0)
    infra_exposure = models.FloatField(default=0.0)
    admin_code = models.CharField(max_length=50, blank=True)
    computed_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"SpatialContext for {self.incident_id}"


