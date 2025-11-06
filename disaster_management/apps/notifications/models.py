from django.db import models
from django.conf import settings

class Notification(models.Model):
    TARGET_TYPE_CHOICES = [
        ('global', 'Global'),
        ('zone', 'Zone'),       # for risk zones or specific locations
        ('user', 'Individual User'),
    ]

    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]

    title = models.CharField(max_length=200)
    message = models.TextField()
    
    target_type = models.CharField(max_length=10, choices=TARGET_TYPE_CHOICES, default='global')
    target_zone = models.ForeignKey('weather.RiskZone', on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')

    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='info')

    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.target_type} ({self.severity})"

class UserNotification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='user_notifications')
    is_read = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} → {self.notification.title}"


class UserDevice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='devices')
    player_id = models.CharField(max_length=255, unique=True)  # OneSignal player ID/token
    device_type = models.CharField(max_length=20, blank=True, null=True)  # e.g., 'web', 'android', 'ios'
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} ({self.device_type})"