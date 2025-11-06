# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Notification


@receiver(post_save, sender=Notification)
def trigger_push_on_create(sender, instance, created, **kwargs):
    if created:
        # You can avoid circular import here by placing logic inline or using celery task
        # Or better: call your utility manually in mutation
        pass  # left blank to avoid double fire if using utility manually
