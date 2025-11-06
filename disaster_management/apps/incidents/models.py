from django.db import models
from django.contrib.gis.db import models as gis_models
from django.utils import timezone
from django.conf import settings

class IncidentType(models.Model):
    TYPE_CHOICES = [
        ("flood", "Flood"),
        ("drought", "Drought"),
        ("fire", "Fire"),
        ("storm", "Storm"),
        ("heatwave", "Heatwave"),
        ("landslide", "Landslide"),
        ("other", "Other"),
    ]

    name = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        unique=True,
        help_text="Disaster type (used to route risk scoring logic)."
    )

    description = models.TextField(blank=True)

    # Optional: if later you use AI-specific models per type
    model_key = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="AI model or rule version for this type (e.g., flood_model_v1)."
    )

    base_weight = models.FloatField(default=1.0)

    def save(self, *args, **kwargs):
        # Automatically attach default descriptions if empty
        if not self.description:
            default_descriptions = {
                "flood": "Overflow or inundation of normally dry land caused by rainfall or river rise.",
                "drought": "Long period of deficient rainfall resulting in water scarcity.",
                "fire": "Uncontrolled burning causing damage to environment or property.",
                "storm": "Severe weather event with strong winds and rain, thunder, or lightning.",
                "heatwave": "Extended period of abnormally high temperatures.",
                "landslide": "Downslope movement of rock or soil due to rain or seismic activity.",
                "other": "Uncategorized disaster or hazard event.",
            }
            self.description = default_descriptions.get(self.name, "")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_name_display()

class Incident(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('responding', 'Responding'),
        ('resolved', 'Resolved'),
    ]

    SOURCE_CHOICES = [
        ("citizen", "Citizen"),
        ("responder", "Responder"),
        ("sensor", "Sensor/IoT"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='incidents')
    incident_type = models.ForeignKey('IncidentType', on_delete=models.CASCADE, related_name='incidents')
    description = models.TextField()
    location = gis_models.PointField(geography=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    incident_source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="citizen")
    verified = models.BooleanField(default=False)

    # AI outputs
    risk_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    risk_label = models.CharField(max_length=10, null=True, blank=True)
    risk_confidence = models.FloatField(null=True, blank=True)
    risk_drivers = models.JSONField(null=True, blank=True)
    ai_version = models.CharField(max_length=50, null=True, blank=True)

    # Relations
    assigned_responder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_incidents"
    )
    nearest_risk_zone = models.ForeignKey(
        "weather.RiskZone",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents"
    )

    reported_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            gis_models.Index(fields=["location"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.incident_type.name} - {self.status} by {self.user.email}"


class IncidentMedia(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='media')
    media_file = models.FileField(upload_to='incidents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Media for Incident {self.incident.id}"

class IncidentComment(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.user} on Incident {self.incident.id}"


class IncidentCluster(models.Model):
    center = gis_models.PointField(geography=True)
    incident_count = models.IntegerField()
    radius_km = models.FloatField(default=3.0)
    dominant_type = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)


class IncidentHotspot(models.Model):
    WINDOW_CHOICES = [("7d","7d"),("30d","30d")]
    window = models.CharField(max_length=10, choices=WINDOW_CHOICES)
    centroid = gis_models.PointField(geography=True)
    area_geom = gis_models.PolygonField(geography=True, null=True, blank=True)
    intensity = models.FloatField()  # e.g., #incidents or risk-weighted density
    dominant_type = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)