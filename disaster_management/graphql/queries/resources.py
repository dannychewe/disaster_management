import graphene
from django.contrib.gis.geos import Point
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from django.db.models import Sum, F, FloatField, Count
from django.utils import timezone
from django.contrib.gis.db.models.functions import Distance
from disaster_management.apps.resources.models import (
    Inventory,
    Resource,
    ResourceDeployment,
    ResourceUnit,
    ResourceRequest,
)
from disaster_management.apps.resources.utils import recommend_restock
from disaster_management.apps.shelters.models import LocationLog
from disaster_management.graphql.permissions import role_required
from disaster_management.graphql.types.resources import ResourceDeploymentType, ResourceType, ResourceUnitType, RestockRecommendation


# -------------------------------------------------------------------
# 📦 Inventory + Stock Reports
# -------------------------------------------------------------------

class InventoryReportType(graphene.ObjectType):
    resource = graphene.Field(ResourceType)
    available = graphene.Int()
    deployed = graphene.Int()


class InventoryLogType(DjangoObjectType):
    class Meta:
        model = Inventory
        fields = (
            "id",
            "resource",
            "quantity",
            "note",
            "batch_id",
            "source_warehouse",
            "added_by",
            "created_at",
        )


# -------------------------------------------------------------------
# 🔍 Resource Management Queries
# -------------------------------------------------------------------

class ResourceManagementQuery(graphene.ObjectType):
    """
    Combines all resource-related queries:
    - All resources
    - Resource units (with filters)
    - Deployments
    - Requests
    """

    # -------------------- Resource Listing --------------------
    all_resources = graphene.List(
        ResourceType,
        category=graphene.String(required=False),
        min_stock=graphene.Int(required=False),
        status=graphene.String(required=False),
    )

    # -------------------- Units --------------------
    all_resource_units = graphene.List(
        ResourceUnitType,
        status=graphene.String(required=False),
        category=graphene.String(required=False),
        near_lat=graphene.Float(required=False),
        near_lng=graphene.Float(required=False),
        radius_km=graphene.Float(required=False),
    )

    # -------------------- Deployments --------------------
    deployment_logs = graphene.List(
        ResourceDeploymentType,
        region_lat=graphene.Float(),
        region_lng=graphene.Float(),
        radius_km=graphene.Float(),
        start_date=graphene.Date(),
        end_date=graphene.Date(),
    )

    # -------------------- Requests --------------------
    my_resource_requests = graphene.List(lambda: ResourceRequestType)
    all_resource_requests = graphene.List(
        lambda: ResourceRequestType,
        status=graphene.String(required=False),
    )

    # -------------------- Inventory & Restock --------------------
    inventory_report = graphene.List(InventoryReportType)
    inventory_logs = graphene.List(
        InventoryLogType,
        resource_id=graphene.ID(required=False),
        batch_id=graphene.String(required=False),
        source_warehouse=graphene.String(required=False),
    )
    low_stock_resources = graphene.List(
        ResourceType, threshold=graphene.Int(default_value=10)
    )
    restock_recommendations = graphene.List(
        RestockRecommendation,
        projected_days=graphene.Int(default_value=3),
        category=graphene.String(required=False),
        region_lat=graphene.Float(required=False),
        region_lng=graphene.Float(required=False),
        radius_km=graphene.Float(required=False),
    )
    
    resource_by_id = graphene.Field(
        ResourceType,
        id=graphene.ID(required=True),
        description="Get a single resource by ID",
    )

    def resolve_resource_by_id(self, info, id):
        try:
            return Resource.objects.get(id=id)
        except Resource.DoesNotExist:
            raise GraphQLError("Resource not found.")

    # ==============================================================
    # RESOLVERS
    # ==============================================================

    # -------------------- Resource List --------------------
    def resolve_all_resources(self, info, category=None, min_stock=None, status=None):
        qs = Resource.objects.all()
        if category:
            qs = qs.filter(category__iexact=category)
        if min_stock is not None:
            qs = [r for r in qs if r.current_stock >= min_stock]
        if status == "low":
            qs = [r for r in qs if r.current_stock < 10]
        return qs

    # -------------------- Units --------------------
    def resolve_all_resource_units(
        self, info, status=None, category=None, near_lat=None, near_lng=None, radius_km=None
    ):
        qs = ResourceUnit.objects.select_related("resource", "assigned_to_user", "assigned_incident")
        if status:
            qs = qs.filter(status=status)
        if category:
            qs = qs.filter(resource__category__iexact=category)
        if near_lat and near_lng and radius_km:
            center = Point(near_lng, near_lat, srid=4326)
            qs = qs.filter(current_location__distance_lte=(center, radius_km * 1000))
        return qs.order_by("-updated_at")

    # -------------------- Deployments --------------------
    def resolve_deployment_logs(self, info, **kwargs):
        queryset = ResourceDeployment.objects.all()
        region_lat = kwargs.get("region_lat")
        region_lng = kwargs.get("region_lng")
        radius_km = kwargs.get("radius_km")
        start_date = kwargs.get("start_date")
        end_date = kwargs.get("end_date")

        if region_lat and region_lng and radius_km:
            center = Point(region_lng, region_lat, srid=4326)
            queryset = queryset.filter(destination__distance_lte=(center, radius_km * 1000))
        if start_date:
            queryset = queryset.filter(deployed_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(deployed_at__date__lte=end_date)

        return queryset.order_by("-deployed_at")

    # -------------------- Requests --------------------
    def resolve_my_resource_requests(self, info):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")
        return ResourceRequest.objects.filter(requester=user).order_by("-created_at")

    def resolve_all_resource_requests(self, info, status=None):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        qs = ResourceRequest.objects.select_related("resource", "requester")

        # ✅ Role-based restriction
        if getattr(user, "role", "") != "Admin":
            qs = qs.filter(requester=user)

        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-created_at")

    # -------------------- Inventory Reports --------------------
    def resolve_inventory_report(self, info):
        report = []
        for res in Resource.objects.all():
            deployed_qty = (
                res.deployments.aggregate(total=Sum("quantity")).get("total") or 0
            )
            report.append(
                InventoryReportType(
                    resource=res,
                    available=res.current_stock,
                    deployed=deployed_qty,
                )
            )
        return report

    def resolve_inventory_logs(
        self, info, resource_id=None, batch_id=None, source_warehouse=None
    ):
        qs = Inventory.objects.all()
        if resource_id:
            qs = qs.filter(resource_id=resource_id)
        if batch_id:
            qs = qs.filter(batch_id=batch_id)
        if source_warehouse:
            qs = qs.filter(source_warehouse__icontains=source_warehouse)
        return qs.order_by("-created_at")

    def resolve_low_stock_resources(self, info, threshold):
        return [r for r in Resource.objects.all() if r.current_stock < threshold]

    # -------------------- Restock AI Recommendations --------------------
    def resolve_restock_recommendations(
        self, info, projected_days, category=None, region_lat=None, region_lng=None, radius_km=None
    ):
        qs = Resource.objects.all()
        if category:
            qs = qs.filter(category__iexact=category)
        if region_lat and region_lng and radius_km:
            center = Point(region_lng, region_lat, srid=4326)
            qs = qs.filter(
                deployments__destination__distance_lte=(center, radius_km * 1000)
            ).distinct()

        recommendations = []
        for res in qs:
            msg = recommend_restock(res, projected_days=projected_days)
            if msg:
                recommendations.append(RestockRecommendation(resource=res, message=msg))
        return recommendations


class ResourceStats(graphene.ObjectType):
    label = graphene.String()
    value = graphene.Float()


class ResourceAnalytics(graphene.ObjectType):
    total_resources = graphene.Int()
    total_stock = graphene.Int()
    total_deployed = graphene.Int()
    low_stock_resources = graphene.Int()
    avg_availability_rate = graphene.Float()
    resources_by_category = graphene.List(ResourceStats)
    restock_recommendations = graphene.List(graphene.String)
    top_deployed_resources = graphene.List(ResourceType)

class ResourceAnalyticsQuery(graphene.ObjectType):
    admin_resource_analytics = graphene.Field(ResourceAnalytics)
    responder_resource_analytics = graphene.Field(ResourceAnalytics)
    citizen_resource_analytics = graphene.Field(ResourceAnalytics, radius_km=graphene.Float(default_value=10.0))

    # ==========================================================
    # 🧠 ADMIN ANALYTICS
    # ==========================================================
    @role_required("Admin")
    def resolve_admin_resource_analytics(self, info):
        total_resources = Resource.objects.count()

        # Aggregate totals
        total_stock = Resource.objects.aggregate(total=Sum("total_stock"))["total"] or 0
        total_deployed = (
            ResourceDeployment.objects.aggregate(total=Sum("quantity"))["total"] or 0
        )

        low_stock_count = sum(1 for r in Resource.objects.all() if r.current_stock < 10)

        avg_availability_rate = (
            Resource.objects.annotate(
                rate=(F("total_stock") - total_deployed) * 100.0 / F("total_stock")
            )
            .aggregate(avg=Sum("rate") / Count("id"))["avg"]
            or 0
        )

        resources_by_category = [
            ResourceStats(label=row["category"], value=row["count"])
            for row in Resource.objects.values("category").annotate(count=Count("id"))
        ]

        # Get top deployed resources
        top_deployed = (
            Resource.objects.annotate(total=Sum("deployments__quantity"))
            .filter(total__gt=0)
            .order_by("-total")[:5]
        )

        # Simple AI-based recommendations
        recommendations = []
        for res in Resource.objects.all():
            msg = recommend_restock(res, projected_days=3)
            if msg:
                recommendations.append(f"{res.name}: {msg}")

        return ResourceAnalytics(
            total_resources=total_resources,
            total_stock=total_stock,
            total_deployed=total_deployed,
            low_stock_resources=low_stock_count,
            avg_availability_rate=round(avg_availability_rate, 2),
            resources_by_category=resources_by_category,
            restock_recommendations=recommendations,
            top_deployed_resources=top_deployed,
        )

    # ==========================================================
    # 🚨 RESPONDER ANALYTICS
    # ==========================================================
    @role_required("Responder")
    def resolve_responder_resource_analytics(self, info):
        user = info.context.user
        assigned_units = ResourceUnit.objects.filter(assigned_to_user=user)
        total_assigned = assigned_units.count()
        deployed = assigned_units.filter(status="deployed").count()
        available = assigned_units.filter(status="available").count()

        # Calculate % utilization
        utilization_rate = (
            (deployed / total_assigned) * 100 if total_assigned > 0 else 0
        )

        # Top resource categories handled
        resources_by_category = [
            ResourceStats(label=row["resource__category"], value=row["count"])
            for row in assigned_units.values("resource__category").annotate(count=Count("id"))
        ]

        return ResourceAnalytics(
            total_resources=total_assigned,
            total_stock=available,
            total_deployed=deployed,
            low_stock_resources=0,
            avg_availability_rate=round(utilization_rate, 2),
            resources_by_category=resources_by_category,
            restock_recommendations=[],
            top_deployed_resources=[],
        )

    # ==========================================================
    # 👥 CITIZEN ANALYTICS
    # ==========================================================
    @role_required("Citizen")
    def resolve_citizen_resource_analytics(self, info, radius_km):
        user = info.context.user
        latest_log = LocationLog.objects.filter(user=user).order_by("-timestamp").first()
        if not latest_log:
            raise GraphQLError("Location data not available for this user.")

        user_location = latest_log.location

        nearby_units = (
            ResourceUnit.objects.filter(status="available")
            .annotate(distance=Distance("current_location", user_location))
            .filter(current_location__distance_lte=(user_location, radius_km * 1000))
        )

        total_nearby = nearby_units.count()
        nearby_by_category = [
            ResourceStats(label=row["resource__category"], value=row["count"])
            for row in nearby_units.values("resource__category").annotate(count=Count("id"))
        ]

        return ResourceAnalytics(
            total_resources=total_nearby,
            total_stock=0,
            total_deployed=0,
            low_stock_resources=0,
            avg_availability_rate=0,
            resources_by_category=nearby_by_category,
            restock_recommendations=[],
            top_deployed_resources=[],
        )


# -------------------------------------------------------------------
# 📦 Main Root Query
# -------------------------------------------------------------------

class ResourcesQuery(ResourceManagementQuery, ResourceAnalyticsQuery, graphene.ObjectType):
    """
    Combines all resource-related subqueries into one schema node.
    """
    pass


# -------------------------------------------------------------------
# 📦 GraphQL Types for Resource Requests (at bottom for imports)
# -------------------------------------------------------------------

class ResourceRequestType(DjangoObjectType):
    class Meta:
        model = ResourceRequest
        fields = (
            "id",
            "resource",
            "quantity",
            "reason",
            "status",
            "requester",
            "created_at",
            "reviewed_by",
            "reviewed_at",
        )
