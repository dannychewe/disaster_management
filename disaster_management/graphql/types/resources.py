






import graphene
from graphene_django import DjangoObjectType

from disaster_management.apps.resources.models import Inventory, Resource, ResourceDeployment, ResourceRequest, ResourceUnit
from disaster_management.graphql.types.core import LocationType


class ResourceType(DjangoObjectType):
    current_stock = graphene.Int()  # expose property
    class Meta:
        model = Resource
        fields = ("id", "name", "category", "total_stock", "updated_at")

    def resolve_current_stock(self, info):
        return self.current_stock
    
class ResourceUnitLocation(graphene.ObjectType):
    latitude = graphene.Float()
    longitude = graphene.Float()
    
class ResourceUnitType(DjangoObjectType):
    current_location = graphene.Field(ResourceUnitLocation)
    class Meta:
        model = ResourceUnit
        exclude = ("current_location",)

    def resolve_current_location(self, info):
        if self.current_location:
            return ResourceUnitLocation(latitude=self.current_location.y, longitude=self.current_location.x)
        return None
    
    
class ResourceRequestType(DjangoObjectType):
    class Meta:
        model = ResourceRequest
        fields = (
            "id",
            "resource",
            "requester",
            "quantity",
            "reason",
            "status",
            "admin_note",
            "created_at",
            "updated_at",
            "reviewed_by",
            "reviewed_at",
        )
        
    def resolve_status(self, info):
        return self.status.upper() if self.status else None

class ResourceDeploymentType(DjangoObjectType):
    destination = graphene.Field(LocationType)
    class Meta:
        model = ResourceDeployment
        exclude = ("destination",)
        
    def resolve_destination(self, info):
        if self.destination:
            return LocationType(latitude=self.destination.y, longitude=self.destination.x)
        return None
        
class RestockRecommendation(graphene.ObjectType):
    resource = graphene.Field(ResourceType)
    message = graphene.String()


class InventoryType(DjangoObjectType):
    class Meta:
        model = Inventory
        fields = (
            "id",
            "resource",
            "quantity",
            "transaction_type",
            "batch_id",
            "source_warehouse",
            "note",
            "created_at",
            "added_by",
        )
