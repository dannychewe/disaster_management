

import graphene
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from graphql import GraphQLError
from django.db.models import Count, Sum, Avg, F, FloatField

from django.contrib.gis.db.models.functions import Distance
from django.utils import timezone
from datetime import timedelta
from disaster_management.apps.incidents.models import Incident
from disaster_management.apps.shelters.models import LocationLog, Shelter, ShelterType
from disaster_management.apps.users.models import User
from disaster_management.graphql.permissions import role_required
from disaster_management.graphql.types.shelters import ShelterNode, ShelterTypeType
from disaster_management.graphql.types.users import UserType
from disaster_management.graphql.types.incidents import IncidentTypeNode

class ShelterQuery(graphene.ObjectType):
    all_active_shelters = graphene.List(ShelterNode)
    shelters_nearby = graphene.List(
        ShelterNode,
        latitude=graphene.Float(required=True),
        longitude=graphene.Float(required=True),
        radius_km=graphene.Float(required=True)
    )
    nearby_incidents = graphene.List(
        IncidentTypeNode,
        shelter_id=graphene.ID(required=True),
        radius_km=graphene.Float(required=True)
    )
    shelter = graphene.Field(ShelterNode, id=graphene.ID(required=True))  # ✅ new
    
    all_shelter_types = graphene.List(ShelterTypeType)  # ✅ new

    # ------------------------------
    # Shelter Types
    # ------------------------------
    def resolve_all_shelter_types(self, info):
        """Return all registered shelter types."""
        return ShelterType.objects.all().order_by("name")

    # ------------------------------
    # Single shelter details
    # ------------------------------
    def resolve_shelter(self, info, id):
        """Fetch a single shelter by its ID."""
        try:
            return Shelter.objects.select_related(
                "shelter_type", "manager"
            ).get(id=id)
        except Shelter.DoesNotExist:
            raise GraphQLError("Shelter not found.")

    # ------------------------------
    # All active shelters
    # ------------------------------
    def resolve_all_active_shelters(self, info):
        return Shelter.objects.filter(is_active=True)

    # ------------------------------
    # Shelters near a given point
    # ------------------------------
    def resolve_shelters_nearby(self, info, latitude, longitude, radius_km):
        user_location = Point(longitude, latitude, srid=4326)
        return (
            Shelter.objects.annotate(distance=Distance("location", user_location))
            .filter(location__distance_lte=(user_location, radius_km * 1000))
            .order_by("distance")
        )

    # ------------------------------
    # Nearby incidents for a shelter
    # ------------------------------
    def resolve_nearby_incidents(self, info, shelter_id, radius_km):
        try:
            shelter = Shelter.objects.get(id=shelter_id)
        except Shelter.DoesNotExist:
            raise GraphQLError("Shelter not found.")

        shelter_location = shelter.location
        if not shelter_location:
            raise GraphQLError("Shelter has no location data.")

        # ✅ Define search area
        search_radius = radius_km * 1000  # meters

        # ✅ Filter out very old or resolved incidents (optional)
        recent_timeframe = timezone.now() - timedelta(days=30)

        incidents = (
            Incident.objects.annotate(
                distance=Distance("location", shelter_location)
            )
            .filter(
                location__distance_lte=(shelter_location, search_radius),
                reported_at__gte=recent_timeframe,
            )
            .exclude(status="resolved")
            .order_by("distance")
        )

        # ✅ Attach distance (in km) to each incident dynamically
        for incident in incidents:
            incident.distance_km = (
                round(incident.distance.m / 1000, 2) if incident.distance else None
            )

        return incidents
        
class TrackingQuery(graphene.ObjectType):
    nearby_responders = graphene.List(UserType, latitude=graphene.Float(), longitude=graphene.Float(), radius_km=graphene.Float())

    def resolve_nearby_responders(self, info, latitude, longitude, radius_km):
        point = Point(longitude, latitude, srid=4326)
        return User.objects.filter(roles__name="Responder", location__distance_lte=(point, radius_km * 1000))

class RouteInfo(graphene.ObjectType):
    shelter = graphene.Field(ShelterNode)
    distance_km = graphene.Float()

class RoutingQuery(graphene.ObjectType):
    nearest_shelter = graphene.Field(
        RouteInfo,
        latitude=graphene.Float(required=True),
        longitude=graphene.Float(required=True)
    )

    def resolve_nearest_shelter(self, info, latitude, longitude):
        point = Point(longitude, latitude, srid=4326)
        shelter = Shelter.objects.filter(is_active=True).annotate(
            distance=Distance("location", point)
        ).order_by("distance").first()

        if not shelter:
            raise GraphQLError("No active shelters found.")

        return RouteInfo(shelter=shelter, distance_km=shelter.distance.km)


class ShelterStats(graphene.ObjectType):
    label = graphene.String()
    value = graphene.Float()


class ShelterAnalytics(graphene.ObjectType):
    total_shelters = graphene.Int()
    active_shelters = graphene.Int()
    total_capacity = graphene.Int()
    total_occupants = graphene.Int()
    avg_occupancy_rate = graphene.Float()
    shelters_by_type = graphene.List(ShelterStats)
    top_overcrowded_shelters = graphene.List(ShelterNode)
    recently_created_shelters = graphene.List(ShelterNode)



class ShelterAnalyticsQuery(graphene.ObjectType):
    admin_shelter_analytics = graphene.Field(ShelterAnalytics)
    responder_shelter_analytics = graphene.Field(ShelterAnalytics)
    citizen_shelter_analytics = graphene.Field(ShelterAnalytics, radius_km=graphene.Float(default_value=10.0))

    # -------------------------------------------------
    # 🧠 ADMIN ANALYTICS
    # -------------------------------------------------
    @role_required("Admin")
    def resolve_admin_shelter_analytics(self, info):
        total_shelters = Shelter.objects.count()
        active_shelters = Shelter.objects.filter(is_active=True).count()

        agg = Shelter.objects.aggregate(
            total_capacity=Sum("capacity"),
            total_occupants=Sum("current_occupants"),
            avg_occupancy=Avg(F("current_occupants") * 100.0 / F("capacity"), output_field=FloatField()),
        )

        shelters_by_type = [
            ShelterStats(label=item["shelter_type__name"] or "Uncategorized", value=item["count"])
            for item in Shelter.objects.values("shelter_type__name").annotate(count=Count("id"))
        ]

        overcrowded = Shelter.objects.annotate(
            occupancy_rate=F("current_occupants") * 100.0 / F("capacity")
        ).filter(occupancy_rate__gt=90).order_by("-occupancy_rate")[:5]

        recent = Shelter.objects.filter(created_at__gte=timezone.now() - timedelta(days=30)).order_by("-created_at")[:5]

        return ShelterAnalytics(
            total_shelters=total_shelters,
            active_shelters=active_shelters,
            total_capacity=agg["total_capacity"] or 0,
            total_occupants=agg["total_occupants"] or 0,
            avg_occupancy_rate=round(agg["avg_occupancy"] or 0, 2),
            shelters_by_type=shelters_by_type,
            top_overcrowded_shelters=overcrowded,
            recently_created_shelters=recent,
        )

    # -------------------------------------------------
    # 🚨 RESPONDER ANALYTICS
    # -------------------------------------------------
    @role_required("Responder")
    def resolve_responder_shelter_analytics(self, info):
        user = info.context.user
        managed = Shelter.objects.filter(manager=user)
        total_managed = managed.count()

        agg = managed.aggregate(
            total_capacity=Sum("capacity"),
            total_occupants=Sum("current_occupants"),
            avg_occupancy=Avg(F("current_occupants") * 100.0 / F("capacity"), output_field=FloatField()),
        )

        overcrowded = managed.annotate(
            occupancy_rate=F("current_occupants") * 100.0 / F("capacity")
        ).filter(occupancy_rate__gt=90).order_by("-occupancy_rate")[:5]

        return ShelterAnalytics(
            total_shelters=total_managed,
            active_shelters=managed.filter(is_active=True).count(),
            total_capacity=agg["total_capacity"] or 0,
            total_occupants=agg["total_occupants"] or 0,
            avg_occupancy_rate=round(agg["avg_occupancy"] or 0, 2),
            shelters_by_type=[],
            top_overcrowded_shelters=overcrowded,
            recently_created_shelters=[],
        )

    # -------------------------------------------------
    # 👥 CITIZEN ANALYTICS
    # -------------------------------------------------
    @role_required("Citizen")
    def resolve_citizen_shelter_analytics(self, info, radius_km):
        user = info.context.user
        latest_log = LocationLog.objects.filter(user=user).order_by("-timestamp").first()
        if not latest_log:
            raise GraphQLError("No location data available for this user.")

        point = latest_log.location

        nearby = (
            Shelter.objects.annotate(distance=Distance("location", point))
            .filter(location__distance_lte=(point, radius_km * 1000))
            .order_by("distance")
        )

        shelters_by_type = [
            ShelterStats(label=item["shelter_type__name"] or "Uncategorized", value=item["count"])
            for item in nearby.values("shelter_type__name").annotate(count=Count("id"))
        ]

        closest = nearby.first()

        return ShelterAnalytics(
            total_shelters=nearby.count(),
            active_shelters=nearby.filter(is_active=True).count(),
            total_capacity=nearby.aggregate(Sum("capacity"))["capacity__sum"] or 0,
            total_occupants=nearby.aggregate(Sum("current_occupants"))["current_occupants__sum"] or 0,
            avg_occupancy_rate=round(
                nearby.aggregate(avg=Avg(F("current_occupants") * 100.0 / F("capacity")))["avg"] or 0, 2
            ),
            shelters_by_type=shelters_by_type,
            top_overcrowded_shelters=[],
            recently_created_shelters=[closest] if closest else [],
        )


class SheltersQuery(ShelterQuery, TrackingQuery, RoutingQuery, ShelterAnalyticsQuery, graphene.ObjectType):
    pass