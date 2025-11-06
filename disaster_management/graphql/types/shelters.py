

import graphene
from graphene_django import DjangoObjectType
from disaster_management.apps.shelters.models import Shelter, ShelterType
from disaster_management.graphql.types.core import LocationType


class ShelterTypeType(DjangoObjectType):
    class Meta:
        model = ShelterType
        fields = ("id", "name", "description")

class ShelterNode(DjangoObjectType):
    location = graphene.Field(LocationType)
    distance_km = graphene.Float()
    
    class Meta:
        model = Shelter

        exclude = ("location",)
        
    def resolve_distance_km(self, info):
        return getattr(self, "distance_km", None)
        
    def resolve_location(self, info):
        if self.location:
            return LocationType(latitude=self.location.y, longitude=self.location.x)
        return None
        
