import graphene
from graphene_django import DjangoObjectType

from disaster_management.apps.core.models import ActivityLog, ErrorLog
from disaster_management.apps.forecasting.models import ForecastModel, ForecastResult
from disaster_management.apps.incidents.models import Incident, IncidentComment, IncidentMedia, IncidentType
from disaster_management.apps.notifications.models import Notification, UserNotification
from disaster_management.apps.resources.models import Inventory, Resource, ResourceDeployment, ResourceRequest, ResourceUnit
from disaster_management.apps.shelters.models import Shelter, ShelterType
from disaster_management.apps.users.models import User
from disaster_management.apps.weather.models import RiskZone, WeatherLog
from disaster_management.graphql.mixins import GeoJSONResolverMixin, GeometryResolverMixin, LocationResolverMixin

import json

from disaster_management.graphql.types.users import UserType
from disaster_management.utils.urls import abs_media_url



        
    
class LocationType(graphene.ObjectType):
    latitude = graphene.Float()
    longitude = graphene.Float()
    
        

class ActivityLogType(DjangoObjectType):
    class Meta:
        model = ActivityLog
        fields = (
            "id",
            "user",
            "action",
            "model_name",
            "object_id",
            "description",
            "timestamp",
        )
        
    user = graphene.Field(UserType)

    def resolve_user(self, info):
        return self.user if self.user else None
    
    
class ErrorLogType(DjangoObjectType):
    class Meta:
        model = ErrorLog
        fields = ("id", "source", "error_message", "stack_trace", "occurred_at")
