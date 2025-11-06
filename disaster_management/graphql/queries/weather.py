

from graphql import GraphQLError
from graphene import List, ObjectType
import graphene
from disaster_management.apps.shelters.models import LocationLog
from disaster_management.apps.weather.models import RiskZone, WeatherLog
from disaster_management.graphql.permissions import role_required
from django.db.models import Count, Avg
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.utils import timezone

from disaster_management.graphql.types.weather import RiskZoneType, WeatherLogType

class Query(ObjectType):
    all_risk_zones = List(RiskZoneType)
    weather_logs = graphene.List(
        WeatherLogType,
        city=graphene.String(required=False),
        date=graphene.Date(required=False),
        limit=graphene.Int(required=False),
        offset=graphene.Int(required=False),
    )

    def resolve_weather_logs(self, info, city=None, date=None, limit=None, offset=None):
        queryset = WeatherLog.objects.all().order_by('-recorded_at')

        if city:
            queryset = queryset.filter(city__icontains=city)

        if date:
            queryset = queryset.filter(recorded_at__date=date)

        if offset:
            queryset = queryset[offset:]
        if limit:
            queryset = queryset[:limit]

        return queryset


    def resolve_all_risk_zones(root, info):
        return RiskZone.objects.all()
    
    
class RiskStats(graphene.ObjectType):
    label = graphene.String()
    value = graphene.Float()

class WeatherAnalytics(graphene.ObjectType):
    total_risk_zones = graphene.Int()
    high_risk_zones = graphene.Int()
    medium_risk_zones = graphene.Int()
    low_risk_zones = graphene.Int()
    avg_temperature = graphene.Float()
    avg_humidity = graphene.Float()
    common_condition = graphene.String()
    risk_distribution = graphene.List(RiskStats)
    recent_weather_logs = graphene.List(WeatherLogType)



class WeatherAnalyticsQuery(graphene.ObjectType):
    admin_weather_analytics = graphene.Field(WeatherAnalytics)
    responder_weather_analytics = graphene.Field(WeatherAnalytics)
    citizen_weather_analytics = graphene.Field(WeatherAnalytics, radius_km=graphene.Float(default_value=10.0))

    # ==========================================================
    # 🧠 ADMIN ANALYTICS
    # ==========================================================
    @role_required("Admin")
    def resolve_admin_weather_analytics(self, info):
        total_zones = RiskZone.objects.count()
        high = RiskZone.objects.filter(risk_level="high").count()
        medium = RiskZone.objects.filter(risk_level="medium").count()
        low = RiskZone.objects.filter(risk_level="low").count()

        weather_qs = WeatherLog.objects.order_by("-recorded_at")[:100]
        avg_temp = weather_qs.aggregate(avg=Avg("temperature"))["avg"] or 0
        avg_humidity = weather_qs.aggregate(avg=Avg("humidity"))["avg"] or 0

        # Most common condition
        condition_counts = (
            weather_qs.values("condition").annotate(count=Count("id")).order_by("-count")
        )
        common_condition = condition_counts[0]["condition"] if condition_counts else "N/A"

        risk_distribution = [
            RiskStats(label="High", value=high),
            RiskStats(label="Medium", value=medium),
            RiskStats(label="Low", value=low),
        ]

        return WeatherAnalytics(
            total_risk_zones=total_zones,
            high_risk_zones=high,
            medium_risk_zones=medium,
            low_risk_zones=low,
            avg_temperature=round(avg_temp, 2),
            avg_humidity=round(avg_humidity, 2),
            common_condition=common_condition,
            risk_distribution=risk_distribution,
            recent_weather_logs=weather_qs,
        )

    # ==========================================================
    # 🚨 RESPONDER ANALYTICS
    # ==========================================================
    @role_required("Responder")
    def resolve_responder_weather_analytics(self, info):
        user = info.context.user
        # Find latest location
        latest_log = LocationLog.objects.filter(user=user).order_by("-timestamp").first()
        if not latest_log:
            raise GraphQLError("No location data available for responder.")

        point = latest_log.location

        # Find nearby high/medium risk zones
        nearby_zones = (
            RiskZone.objects.annotate(distance=Distance("geometry", point))
            .filter(distance__lte=50000)  # 50 km radius
            .order_by("distance")
        )

        high = nearby_zones.filter(risk_level="high").count()
        medium = nearby_zones.filter(risk_level="medium").count()
        low = nearby_zones.filter(risk_level="low").count()

        recent_weather = (
            WeatherLog.objects.annotate(distance=Distance("location", point))
            .filter(location__distance_lte=(point, 50000))
            .order_by("-recorded_at")[:10]
        )

        return WeatherAnalytics(
            total_risk_zones=nearby_zones.count(),
            high_risk_zones=high,
            medium_risk_zones=medium,
            low_risk_zones=low,
            avg_temperature=recent_weather.aggregate(avg=Avg("temperature"))["avg"] or 0,
            avg_humidity=recent_weather.aggregate(avg=Avg("humidity"))["avg"] or 0,
            common_condition=(
                recent_weather.values("condition")
                .annotate(count=Count("id"))
                .order_by("-count")
                .first()
            )["condition"]
            if recent_weather.exists()
            else "N/A",
            risk_distribution=[
                RiskStats(label="High", value=high),
                RiskStats(label="Medium", value=medium),
                RiskStats(label="Low", value=low),
            ],
            recent_weather_logs=recent_weather,
        )

    # ==========================================================
    # 👥 CITIZEN ANALYTICS
    # ==========================================================
    @role_required("Citizen")
    def resolve_citizen_weather_analytics(self, info, radius_km):
        user = info.context.user
        latest_log = LocationLog.objects.filter(user=user).order_by("-timestamp").first()
        if not latest_log:
            raise GraphQLError("No location data available for this user.")

        point = latest_log.location

        # Nearby weather logs
        nearby_weather = (
            WeatherLog.objects.annotate(distance=Distance("location", point))
            .filter(location__distance_lte=(point, radius_km * 1000))
            .order_by("-recorded_at")[:10]
        )

        # Closest risk zone
        nearby_zones = (
            RiskZone.objects.annotate(distance=Distance("geometry", point))
            .filter(distance__lte=radius_km * 1000)
            .order_by("distance")
        )

        high = nearby_zones.filter(risk_level="high").count()
        medium = nearby_zones.filter(risk_level="medium").count()
        low = nearby_zones.filter(risk_level="low").count()

        return WeatherAnalytics(
            total_risk_zones=nearby_zones.count(),
            high_risk_zones=high,
            medium_risk_zones=medium,
            low_risk_zones=low,
            avg_temperature=nearby_weather.aggregate(avg=Avg("temperature"))["avg"] or 0,
            avg_humidity=nearby_weather.aggregate(avg=Avg("humidity"))["avg"] or 0,
            common_condition=(
                nearby_weather.values("condition")
                .annotate(count=Count("id"))
                .order_by("-count")
                .first()
            )["condition"]
            if nearby_weather.exists()
            else "N/A",
            risk_distribution=[
                RiskStats(label="High", value=high),
                RiskStats(label="Medium", value=medium),
                RiskStats(label="Low", value=low),
            ],
            recent_weather_logs=nearby_weather,
        )


class WeatherQuery(
    Query,
    WeatherAnalyticsQuery,
    graphene.ObjectType
):
    pass