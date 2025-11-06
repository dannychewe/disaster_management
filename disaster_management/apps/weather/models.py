from django.db import models
from django.contrib.gis.db import models as gis_models
from django.utils import timezone

class RiskZone(models.Model):
    RISK_LEVEL_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    zone_name = models.CharField(max_length=150)
    geometry = gis_models.PolygonField(geography=True)
    risk_level = models.CharField(max_length=10, choices=RISK_LEVEL_CHOICES)

    calculated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.zone_name} ({self.risk_level})"

class HistoricalIncident(models.Model):
    incident_type = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    location = gis_models.PointField(geography=True)
    occurred_at = models.DateTimeField()

    def __str__(self):
        return f"{self.incident_type} @ {self.occurred_at.strftime('%Y-%m-%d')}"


class WeatherLog(models.Model):
    temperature = models.FloatField()
    humidity = models.FloatField()
    wind_speed = models.FloatField()
    condition = models.CharField(max_length=100)  # e.g., "Rain", "Clear", "Storm"

    location = gis_models.PointField(geography=True)
    city_name = models.CharField(max_length=100, blank=True, null=True)
    recorded_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.city_name} - {self.condition} at {self.recorded_at.strftime('%Y-%m-%d %H:%M')}"

class DataSource(models.Model):
    name = models.CharField(max_length=100, unique=True)  # e.g., "OpenWeatherMap"
    base_url = models.URLField()
    api_key = models.CharField(max_length=255)
    active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({'Active' if self.active else 'Inactive'})"