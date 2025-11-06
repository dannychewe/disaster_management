from django.db import models
from django.conf import settings

class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('view', 'View'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('custom', 'Custom'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='custom')
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} {self.model_name} ({self.object_id})"

class ErrorLog(models.Model):
    source = models.CharField(max_length=255)
    error_message = models.TextField()
    stack_trace = models.TextField(blank=True, null=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Error in {self.source} @ {self.occurred_at.strftime('%Y-%m-%d %H:%M')}"
