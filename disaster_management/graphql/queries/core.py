


import graphene

from disaster_management.apps.core.models import ActivityLog, ErrorLog
from disaster_management.graphql.types.core import ActivityLogType, ErrorLogType



class LogQuery(graphene.ObjectType):
    activity_logs = graphene.List(graphene.NonNull(ActivityLogType))
    error_logs = graphene.List(graphene.NonNull(ErrorLogType))

    def resolve_activity_logs(self, info):
        return ActivityLog.objects.select_related("user").order_by('-timestamp')[:100]

    def resolve_error_logs(self, info):
        return ErrorLog.objects.order_by('-occurred_at')[:100]


class LogsQuery(LogQuery, graphene.ObjectType):
    pass    