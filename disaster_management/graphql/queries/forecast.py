

import graphene


import graphene
from graphene.types.generic import GenericScalar
from django.db.models import Count
from django.utils import timezone
from django.contrib.gis.geos import Polygon, Point
from django.contrib.gis.measure import D


from disaster_management.apps.forecasting.models import ForecastResult
from disaster_management.graphql.types.forecast import ForecastResultType

# ── Enums ──────────────────────────────────────────────────────────────
class RiskLevelEnum(graphene.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ModelTypeEnum(graphene.Enum):
    FLOOD = "flood"
    DROUGHT = "drought"
    HEAT_WAVE = "heat_wave"
    RESOURCE_SHORTAGE = "resource_shortage"

class ForecastOrderEnum(graphene.Enum):
    NEWEST = "NEWEST"
    OLDEST = "OLDEST"
    HIGHEST_CONFIDENCE = "HIGHEST_CONFIDENCE"
    LOWEST_CONFIDENCE = "LOWEST_CONFIDENCE"

# ── Geo inputs ─────────────────────────────────────────────────────────
class BBoxInput(graphene.InputObjectType):
    min_lon = graphene.Float(required=True)
    min_lat = graphene.Float(required=True)
    max_lon = graphene.Float(required=True)
    max_lat = graphene.Float(required=True)

class NearPointInput(graphene.InputObjectType):
    lon = graphene.Float(required=True)
    lat = graphene.Float(required=True)
    radius_km = graphene.Float(required=False, default_value=10.0)

# ── Summary type ───────────────────────────────────────────────────────
class ForecastResultsSummary(graphene.ObjectType):
    total = graphene.Int()
    by_risk = GenericScalar()
    by_model_type = GenericScalar()
    last_updated = graphene.DateTime()

class Query(graphene.ObjectType):
    forecast_results = graphene.List(
        ForecastResultType,
        model_types=graphene.List(ModelTypeEnum),
        risk_levels=graphene.List(RiskLevelEnum),
        area_name=graphene.String(),
        start_date=graphene.Date(),
        end_date=graphene.Date(),
        min_confidence=graphene.Float(),
        bbox=graphene.Argument(BBoxInput),
        near=graphene.Argument(NearPointInput),
        order_by=graphene.Argument(ForecastOrderEnum, default_value=ForecastOrderEnum.NEWEST),
        limit=graphene.Int(default_value=200),
        skip_geometry=graphene.Boolean(default_value=False, description="If true, omits geometry computation work."),
    )

    forecast_results_summary = graphene.Field(
        ForecastResultsSummary,
        model_types=graphene.List(ModelTypeEnum),
        risk_levels=graphene.List(RiskLevelEnum),
        start_date=graphene.Date(),
        end_date=graphene.Date(),
        min_confidence=graphene.Float(),
    )

    # ── Resolvers ──────────────────────────────────────────────────────
    def resolve_forecast_results(
        self,
        info,
        model_types=None,
        risk_levels=None,
        area_name=None,
        start_date=None,
        end_date=None,
        min_confidence=None,
        bbox=None,
        near=None,
        order_by=ForecastOrderEnum.NEWEST,
        limit=200,
        skip_geometry=False,
    ):
        qs = (
            ForecastResult.objects
            .select_related("model")
            .only(
                "id", "forecast_date", "predicted_at", "area_name",
                "risk_level", "confidence", "details",
                "affected_area", "model__name", "model__model_type",
            )
        )

        if model_types:
            qs = qs.filter(model__model_type__in=[mt.value for mt in model_types])

        if risk_levels:
            qs = qs.filter(risk_level__in=[rl.value for rl in risk_levels])

        if area_name:
            qs = qs.filter(area_name__icontains=area_name)

        if start_date:
            qs = qs.filter(forecast_date__gte=start_date)

        if end_date:
            qs = qs.filter(forecast_date__lte=end_date)

        if min_confidence is not None:
            qs = qs.filter(confidence__gte=min_confidence)

        # Geo filters (only if we have geometries)
        if bbox:
            # Construct a bbox polygon (lon/lat order; SRID 4326)
            poly = Polygon.from_bbox((bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat))
            poly.srid = 4326
            qs = qs.filter(affected_area__intersects=poly)

        if near:
            pt = Point(float(near.lon), float(near.lat), srid=4326)
            qs = qs.filter(affected_area__distance_lte=(pt, D(km=float(near.radius_km or 10.0))))

        # Ordering
        if order_by == ForecastOrderEnum.NEWEST:
            qs = qs.order_by("-forecast_date", "-predicted_at")
        elif order_by == ForecastOrderEnum.OLDEST:
            qs = qs.order_by("forecast_date", "predicted_at")
        elif order_by == ForecastOrderEnum.HIGHEST_CONFIDENCE:
            qs = qs.order_by("-confidence", "-forecast_date")
        elif order_by == ForecastOrderEnum.LOWEST_CONFIDENCE:
            qs = qs.order_by("confidence", "-forecast_date")

        # Limit (hard cap to protect API)
        hard_cap = 2000
        limit = min(max(1, int(limit)), hard_cap)
        qs = qs[:limit]

        # If clients don't need geometry, we can strip it early to save work
        if skip_geometry:
            # We already excluded `affected_area` from default fields in the type, so nothing else to do.
            # (The resolver for geometry won't be called unless requested.)
            pass

        return qs

    def resolve_forecast_results_summary(
        self,
        info,
        model_types=None,
        risk_levels=None,
        start_date=None,
        end_date=None,
        min_confidence=None,
    ):
        qs = ForecastResult.objects.all()

        if model_types:
            qs = qs.filter(model__model_type__in=[mt.value for mt in model_types])

        if risk_levels:
            qs = qs.filter(risk_level__in=[rl.value for rl in risk_levels])

        if start_date:
            qs = qs.filter(forecast_date__gte=start_date)

        if end_date:
            qs = qs.filter(forecast_date__lte=end_date)

        if min_confidence is not None:
            qs = qs.filter(confidence__gte=min_confidence)

        # Counts by risk
        risk_counts = dict(qs.values_list("risk_level").annotate(c=Count("id")))

        # Counts by model_type
        type_counts = dict(
            qs.values_list("model__model_type").annotate(c=Count("id"))
        )

        # Most recent prediction time
        last_obj = qs.only("predicted_at").order_by("-predicted_at").first()
        last_updated = getattr(last_obj, "predicted_at", None)

        return ForecastResultsSummary(
            total=qs.count(),
            by_risk=risk_counts,
            by_model_type=type_counts,
            last_updated=last_updated,
        )


class ForecastQuery(Query, graphene.ObjectType):
    pass