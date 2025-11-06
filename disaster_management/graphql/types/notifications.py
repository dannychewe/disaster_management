


from graphene_django import DjangoObjectType

from disaster_management.apps.notifications.models import Notification, UserNotification


class NotificationType(DjangoObjectType):
    class Meta:
        model = Notification
        fields = (
            "id",
            "title",
            "message",
            "severity",
            "target_type",
            "target_zone",
            "triggered_by",
            "sent_at",
        )
        
class UserNotificationType(DjangoObjectType):
    class Meta:
        model = UserNotification
        fields = (
            "id",
            "notification",
            "is_read",
            "received_at",
        )

