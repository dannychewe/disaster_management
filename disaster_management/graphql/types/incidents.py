



import graphene
from graphene_django import DjangoObjectType

from disaster_management.apps.incidents.models import Incident, IncidentComment, IncidentMedia, IncidentType
from disaster_management.graphql.types.resources import ResourceDeploymentType
from disaster_management.utils.urls import abs_media_url


class IncidentTypeType(DjangoObjectType):
    risk_score = graphene.Float()
    
    class Meta:
        model = IncidentType
        fields = ("id", "name")
        
    def resolve_risk_score(self, info):
        return float(self.risk_score) if self.risk_score is not None else None

class IncidentMediaType(DjangoObjectType):
    media_file = graphene.String()

    class Meta:
        model = IncidentMedia
        fields = ("id", "media_file", "uploaded_at")

    def resolve_media_file(self, info):
        return abs_media_url(self.media_file.name, info.context)

class IncidentCommentType(DjangoObjectType):
    class Meta:
        model = IncidentComment
        fields = ("id", "user", "comment", "created_at")
        
class LocationType(graphene.ObjectType):
    latitude = graphene.Float()
    longitude = graphene.Float()
    
class IncidentTypeNode(DjangoObjectType):
    location = graphene.Field(LocationType)
    resources = graphene.List(lambda:ResourceDeploymentType)  # 👈 Add this
    assigned_responder = graphene.Field("disaster_management.graphql.types.UserType")

    class Meta:
        model = Incident
        exclude = ("location",)

    def resolve_location(self, info):
        if self.location:
            return LocationType(latitude=self.location.y, longitude=self.location.x)
        return None

    def resolve_resources(self, info):
        return self.deployments.select_related("resource").all()
    
    def resolve_assigned_responder(self, info):
        """Return responder details if assigned."""
        return self.assigned_responder if self.assigned_responder else None

