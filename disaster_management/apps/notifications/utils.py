# utils/notifications.py

from .models import Notification, UserNotification, UserDevice
from disaster_management.apps.weather.models import RiskZone
from django.conf import settings
import requests

def send_push(player_ids, title, message, data=None):
    """
    Fire push via OneSignal.
    """
    headers = {
        "Authorization": f"Basic {settings.ONESIGNAL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "app_id": settings.ONESIGNAL_APP_ID,
        "include_player_ids": player_ids,
        "headings": {"en": title},
        "contents": {"en": message},
        "data": data or {},
    }

    response = requests.post("https://onesignal.com/api/v1/notifications", json=payload, headers=headers)
    return response.status_code, response.json()


def create_and_send_notification(title, message, severity="info", target_type="global", target_zone=None, user=None, triggered_by=None):
    """
    Utility to create a Notification and send push.
    """
    notification = Notification.objects.create(
        title=title,
        message=message,
        severity=severity,
        target_type=target_type,
        target_zone=target_zone,
        triggered_by=triggered_by
    )

    # Determine recipients
    if target_type == "global":
        users = settings.AUTH_USER_MODEL.objects.filter(is_active=True)
    elif target_type == "zone" and target_zone:
        users = settings.AUTH_USER_MODEL.objects.filter(location__intersects=target_zone.geometry)
    elif target_type == "user" and user:
        users = [user]
    else:
        users = []

    player_ids = []
    for u in users:
        UserNotification.objects.create(user=u, notification=notification)
        player_ids += list(UserDevice.objects.filter(user=u).values_list("player_id", flat=True))

    if player_ids:
        send_push(player_ids, title, message)

    return notification
