

import graphene
from graphql import GraphQLError

from disaster_management.apps.notifications.models import Notification, UserNotification
from graphql_jwt.decorators import login_required

from disaster_management.graphql.types.notifications import NotificationType, UserNotificationType

class NotificationQuery(graphene.ObjectType):
    my_notifications = graphene.List(
        UserNotificationType,
        unread_only=graphene.Boolean(default_value=False)
    )

    @login_required
    def resolve_my_notifications(self, info, unread_only):
        user = info.context.user
        queryset = UserNotification.objects.filter(user=user)

        if unread_only:
            queryset = queryset.filter(is_read=False)

        return queryset.order_by("-received_at")
    
    
    
class AdminNotificationQuery(graphene.ObjectType):
    all_notifications = graphene.List(NotificationType)

    def resolve_all_notifications(self, info):
        user = info.context.user
        if not user.is_authenticated or not user.roles.filter(name="Admin").exists():
            raise GraphQLError("Permission denied. Admins only.")
        return Notification.objects.all().order_by("-sent_at")
    
    
class NotificationsQuery(NotificationQuery, AdminNotificationQuery, graphene.ObjectType):
    pass