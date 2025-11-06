



from django.contrib.auth import get_user_model
import graphene
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from disaster_management.apps.notifications.models import UserNotification
from disaster_management.apps.notifications.utils import create_and_send_notification
from disaster_management.apps.weather.models import RiskZone
from disaster_management.graphql.types.notifications import NotificationType, UserNotificationType

User = get_user_model()

class SendNotification(graphene.Mutation):
    class Arguments:
        title = graphene.String(required=True)
        message = graphene.String(required=True)
        severity = graphene.String(required=False, default_value="info")  # info, warning, critical
        target_type = graphene.String(required=False, default_value="global")  # global, zone, user
        target_zone_id = graphene.ID(required=False)
        target_user_id = graphene.ID(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    notification = graphene.Field(NotificationType)

    @login_required
    def mutate(self, info, title, message, severity, target_type, target_zone_id=None, target_user_id=None):
        user = info.context.user

        if not user.roles.filter(name="Admin").exists():
            raise GraphQLError("Only Admins can send notifications.")

        # Resolve target_zone or target_user if applicable
        target_zone = None
        target_user = None

        if target_type == "zone":
            if not target_zone_id:
                raise GraphQLError("Zone ID is required for zone notifications.")
            try:
                target_zone = RiskZone.objects.get(id=target_zone_id)
            except RiskZone.DoesNotExist:
                raise GraphQLError("Zone not found.")

        if target_type == "user":
            if not target_user_id:
                raise GraphQLError("User ID is required for individual user notifications.")
            try:
                target_user = User.objects.get(id=target_user_id)
            except User.DoesNotExist:
                raise GraphQLError("User not found.")

        notification = create_and_send_notification(
            title=title,
            message=message,
            severity=severity,
            target_type=target_type,
            target_zone=target_zone,
            user=target_user,
            triggered_by=user
        )

        return SendNotification(
            success=True,
            message="Notification sent.",
            notification=notification
        )
        
        
class MarkNotificationAsRead(graphene.Mutation):
    class Arguments:
        notification_id = graphene.ID(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    user_notification = graphene.Field(UserNotificationType)

    @login_required
    def mutate(self, info, notification_id):
        user = info.context.user

        try:
            user_notification = UserNotification.objects.get(
                id=notification_id,
                user=user
            )
        except UserNotification.DoesNotExist:
            raise GraphQLError("Notification not found.")

        if user_notification.is_read:
            return MarkNotificationAsRead(
                success=True,
                message="Notification already marked as read.",
                user_notification=user_notification
            )

        user_notification.is_read = True
        user_notification.save()

        return MarkNotificationAsRead(
            success=True,
            message="Notification marked as read.",
            user_notification=user_notification
        )
        
class MarkAllNotificationsAsRead(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    count = graphene.Int()

    @login_required
    def mutate(self, info):
        user = info.context.user
        updated = UserNotification.objects.filter(user=user, is_read=False).update(is_read=True)
        return MarkAllNotificationsAsRead(
            success=True,
            message=f"{updated} notifications marked as read.",
            count=updated
        )
        
class NotificationMutation(graphene.ObjectType):
    send_notification = SendNotification.Field()
    mark_notification_as_read = MarkNotificationAsRead.Field()
    mark_all_notifications_as_read = MarkAllNotificationsAsRead.Field()