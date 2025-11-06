

import json
import graphene
from graphene_django import DjangoObjectType

from disaster_management.apps.weather.models import RiskZone, WeatherLog
from disaster_management.graphql.types.core import LocationType


class WeatherLogType(DjangoObjectType):
    location = graphene.Field(LocationType)

    class Meta:
        model = WeatherLog
        exclude = ("location",)

    def resolve_location(self, info):
        if self.location:
            return LocationType(latitude=self.location.y, longitude=self.location.x)
        return None


class PolygonCoordinatesType(graphene.ObjectType):
    coordinates = graphene.List(graphene.List(graphene.List(graphene.Float)))

class RiskZoneType(DjangoObjectType):
    geometry = graphene.JSONString()

    class Meta:
        model = RiskZone
        exclude = ("geometry",)

    def resolve_geometry(self, info):
        if not self.geometry:
            return None
        try:
            return json.loads(self.geometry.geojson)
        except Exception:
            return None
