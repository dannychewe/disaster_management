import graphene
from graphene_django import DjangoObjectType
from disaster_management.apps.incidents.models import IncidentHotspot

class HotspotType(DjangoObjectType):
    class Meta:
        model = IncidentHotspot
        fields = ("id","window","intensity","dominant_type","centroid","area_geom","created_at")

class HotspotQuery(graphene.ObjectType):
    hotspots = graphene.List(HotspotType, window=graphene.String(required=True))

    def resolve_hotspots(self, info, window):
        return IncidentHotspot.objects.filter(window=window).order_by("-intensity")[:200]
