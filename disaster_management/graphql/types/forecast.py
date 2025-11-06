



import json
import graphene
from graphene_django import DjangoObjectType

from disaster_management.apps.forecasting.models import ForecastModel, ForecastResult


class ForecastModelType(DjangoObjectType):
    class Meta:
        model = ForecastModel
        fields = ("id", "name", "model_type", "description", "version", "created_at")


class ForecastResultType(DjangoObjectType):
    affected_area = graphene.JSONString()  # <– Add manually
    model = graphene.Field(ForecastModelType)  # <– Add manually

    class Meta:
        model = ForecastResult
        exclude = ("affected_area",)  # prevent graphene from auto-mapping it

    def resolve_affected_area(self, info):
        """Return GeoJSON for Mapbox or frontend."""
        if not self.affected_area:
            return None
        try:
            return json.loads(self.affected_area.geojson)  # convert Polygon to GeoJSON
        except Exception:
            return None
        