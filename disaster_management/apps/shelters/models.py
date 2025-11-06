from django.db import models
from django.contrib.gis.db import models as gis_models
from django.conf import settings
from django.utils import timezone

class ShelterType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Shelter(models.Model):
    name = models.CharField(max_length=150)
    shelter_type = models.ForeignKey(ShelterType, on_delete=models.SET_NULL, null=True, related_name='shelters')

    description = models.TextField(blank=True)

    capacity = models.PositiveIntegerField()
    current_occupants = models.PositiveIntegerField(default=0)

    location = gis_models.PointField(geography=True)

    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_shelters')

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.shelter_type.name if self.shelter_type else 'N/A'})"
    
    

class LocationLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="location_logs")
    location = gis_models.PointField(geography=True)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.email} at {self.timestamp}"
