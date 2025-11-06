from graphene import ID, Field, Float, List, ObjectType, String
from django.contrib.gis.geos import Polygon
import graphene
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from django.db.models import Count, Avg
from django.utils import timezone
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from disaster_management.apps.incidents.models import Incident, IncidentType
from disaster_management.apps.shelters.models import LocationLog, Shelter
from disaster_management.graphql.permissions import role_required
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point

from disaster_management.graphql.types.incidents import IncidentTypeNode, IncidentTypeType
from disaster_management.graphql.types.shelters import ShelterNode

class IncidentQuery(ObjectType):
    all_incidents = List(
        IncidentTypeNode,
        type_id=ID(required=False),
        status=String(required=False),
        min_lat=Float(required=False),
        min_lng=Float(required=False),
        max_lat=Float(required=False),
        max_lng=Float(required=False),
    )
    my_incidents = List(IncidentTypeNode)
    incident = Field(IncidentTypeNode, id=ID(required=True))
    
    nearby_shelters = List(
        ShelterNode,
        latitude=Float(required=True),
        longitude=Float(required=True),
        radius_km=Float(required=True),
    )
    
    
    @login_required
    def resolve_nearby_shelters(self, info, latitude, longitude, radius_km):
        """
        Return active shelters within the given radius of a given point.
        Typically used to find safe shelters near an incident.
        """
        try:
            user = info.context.user
            point = Point(longitude, latitude, srid=4326)

            # Only active shelters within distance
            queryset = (
                Shelter.objects.filter(is_active=True)
                .annotate(distance=Distance("location", point))
                .filter(location__distance_lte=(point, radius_km * 1000))
                .order_by("distance")
            )

            # Attach distance_km property for GraphQL
            for s in queryset:
                s.distance_km = round(s.distance.m / 1000, 2) if s.distance else None

            return queryset

        except Exception as e:
            raise GraphQLError(f"Failed to fetch nearby shelters: {str(e)}")


    # ✅ Single incident resolver
    @login_required
    def resolve_incident(self, info, id):
        user = info.context.user
        try:
            incident = (
                Incident.objects.select_related("incident_type", "user", "assigned_responder")
                .prefetch_related("media")
                .get(id=id)
            )
        except Incident.DoesNotExist:
            raise GraphQLError("Incident not found.")

        # Access control rules
        if user.role == "Citizen" and incident.user != user:
            raise GraphQLError("You are not authorized to view this incident.")
        if user.role == "Responder" and incident.assigned_responder != user:
            raise GraphQLError("You are not authorized to view this incident.")

        return incident

    # ✅ All incidents — Admin sees all, Responder sees assigned only
    @login_required
    @role_required("Admin", "Responder")
    def resolve_all_incidents(
        self, info, type_id=None, status=None, min_lat=None, min_lng=None, max_lat=None, max_lng=None
    ):
        user = info.context.user

        # Base queryset
        if user.role == "Admin":
            queryset = Incident.objects.all()
        else:  # Responder
            queryset = Incident.objects.filter(assigned_responder=user)

        queryset = queryset.select_related("incident_type", "user", "assigned_responder").prefetch_related("media")

        if type_id:
            queryset = queryset.filter(incident_type_id=type_id)
        if status:
            queryset = queryset.filter(status=status)
        if all(v is not None for v in [min_lat, min_lng, max_lat, max_lng]):
            polygon = Polygon.from_bbox((min_lng, min_lat, max_lng, max_lat))
            queryset = queryset.filter(location__within=polygon)

        return queryset.order_by("-reported_at")

    # ✅ My incidents
    @login_required
    def resolve_my_incidents(self, info):
        user = info.context.user
        queryset = (
            Incident.objects.filter(user=user)
            .select_related("incident_type", "user", "assigned_responder")
            .prefetch_related("media")
            .order_by("-reported_at")
        )
        return queryset


class IncidentTypeQuery(ObjectType):
    all_incident_types = List(IncidentTypeType)
    incident_type = Field(IncidentTypeType, id=ID(required=True))

    def resolve_all_incident_types(self, info):
        try:
            return IncidentType.objects.all().order_by("name")
        except Exception as e:
            raise GraphQLError(f"Failed to load incident types: {str(e)}")

    def resolve_incident_type(self, info, id):
        try:
            return IncidentType.objects.get(id=id)
        except IncidentType.DoesNotExist:
            raise GraphQLError("Incident type not found.")

class IncidentStats(graphene.ObjectType):
    label = graphene.String()
    value = graphene.Float()

class IncidentAnalytics(graphene.ObjectType):
    total_incidents = graphene.Int()
    pending = graphene.Int()
    responding = graphene.Int()
    resolved = graphene.Int()
    avg_risk_score = graphene.Float()
    incidents_by_type = graphene.List(IncidentStats)
    monthly_trend = graphene.List(IncidentStats)


class IncidentAnalyticsQuery(graphene.ObjectType):
    admin_incident_analytics = graphene.Field(IncidentAnalytics)
    responder_incident_analytics = graphene.Field(IncidentAnalytics)
    citizen_incident_analytics = graphene.Field(IncidentAnalytics, radius_km=graphene.Float(default_value=10.0))

    # ==========================================================
    # 🧠 ADMIN ANALYTICS
    # ==========================================================
    @role_required("Admin")
    def resolve_admin_incident_analytics(self, info):
        now = timezone.now()
        last_30_days = now - timezone.timedelta(days=30)
        qs = Incident.objects.filter(reported_at__gte=last_30_days)

        total = qs.count()
        pending = qs.filter(status="pending").count()
        responding = qs.filter(status="responding").count()
        resolved = qs.filter(status="resolved").count()

        avg_risk = qs.aggregate(avg=Avg("risk_score"))["avg"] or 0.0

        # By incident type
        by_type = [
            IncidentStats(label=row["incident_type__name"], value=row["count"])
            for row in qs.values("incident_type__name").annotate(count=Count("id")).order_by("-count")
        ]

        # By month (trend)
        month_trend = [
            IncidentStats(label=row["month"], value=row["count"])
            for row in (
                qs.extra(select={"month": "DATE_TRUNC('month', reported_at)"})
                .values("month")
                .annotate(count=Count("id"))
                .order_by("month")
            )
        ]

        return IncidentAnalytics(
            total_incidents=total,
            pending=pending,
            responding=responding,
            resolved=resolved,
            avg_risk_score=round(avg_risk, 2),
            incidents_by_type=by_type,
            monthly_trend=month_trend,
        )

    # ==========================================================
    # 🚨 RESPONDER ANALYTICS
    # ==========================================================
    @role_required("Responder")
    def resolve_responder_incident_analytics(self, info):
        user = info.context.user
        qs = Incident.objects.filter(assigned_responder=user)

        total = qs.count()
        resolved = qs.filter(status="resolved").count()
        responding = qs.filter(status="responding").count()
        pending = qs.filter(status="pending").count()

        avg_risk = qs.aggregate(avg=Avg("risk_score"))["avg"] or 0.0
        resolve_rate = (resolved / total * 100) if total > 0 else 0

        by_type = [
            IncidentStats(label=row["incident_type__name"], value=row["count"])
            for row in qs.values("incident_type__name").annotate(count=Count("id")).order_by("-count")
        ]

        return IncidentAnalytics(
            total_incidents=total,
            pending=pending,
            responding=responding,
            resolved=resolved,
            avg_risk_score=round(avg_risk, 2),
            incidents_by_type=by_type,
            monthly_trend=[
                IncidentStats(label="Resolved %", value=round(resolve_rate, 2))
            ],
        )

    # ==========================================================
    # 👥 CITIZEN ANALYTICS
    # ==========================================================
    @role_required("Citizen")
    def resolve_citizen_incident_analytics(self, info, radius_km):
        user = info.context.user
        reported = Incident.objects.filter(user=user)
        total = reported.count()
        resolved = reported.filter(status="resolved").count()
        responding = reported.filter(status="responding").count()
        pending = reported.filter(status="pending").count()
        avg_risk = reported.aggregate(avg=Avg("risk_score"))["avg"] or 0.0

        # Optional: incidents nearby user location
        latest_log = LocationLog.objects.filter(user=user).order_by("-timestamp").first()
        nearby_count = 0
        if latest_log:
            point = latest_log.location
            nearby_count = (
                Incident.objects.annotate(distance=Distance("location", point))
                .filter(location__distance_lte=(point, radius_km * 1000))
                .exclude(user=user)
                .count()
            )

        by_type = [
            IncidentStats(label=row["incident_type__name"], value=row["count"])
            for row in reported.values("incident_type__name").annotate(count=Count("id")).order_by("-count")
        ]

        return IncidentAnalytics(
            total_incidents=total,
            pending=pending,
            responding=responding,
            resolved=resolved,
            avg_risk_score=round(avg_risk, 2),
            incidents_by_type=by_type,
            monthly_trend=[
                IncidentStats(label="Nearby Incidents", value=nearby_count)
            ],
        )

class IncidentsQuery(IncidentQuery, IncidentTypeQuery, IncidentAnalyticsQuery, graphene.ObjectType):
    """Combined entry point for all incident-related queries."""
    pass
