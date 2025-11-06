from django.contrib import admin
from django.utils.html import format_html
from django.contrib.gis.admin import OSMGeoAdmin

from .models import (
    Resource,
    ResourceUnit,
    ResourceDeployment,
    Inventory,
    ResourceRequest,
)


# ==========================
# 🔹 RESOURCE ADMIN
# ==========================
@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "total_stock", "current_stock", "updated_at")
    list_filter = ("category",)
    search_fields = ("name", "category")
    readonly_fields = ("current_stock",)
    ordering = ("-updated_at",)

    def current_stock(self, obj):
        return obj.current_stock
    current_stock.short_description = "Current Stock"


# ==========================
# 🔹 RESOURCE UNIT ADMIN
# ==========================
@admin.register(ResourceUnit)
class ResourceUnitAdmin(OSMGeoAdmin):
    list_display = (
        "id",
        "resource",
        "serial_number",
        "status",
        "assigned_to_user",
        "assigned_incident",
        "is_available",
        "updated_at",
    )
    list_filter = ("status", "resource__category")
    search_fields = ("serial_number", "resource__name", "assigned_to_user__email")
    default_lon = 28.3  # Center on Zambia roughly
    default_lat = -15.4
    default_zoom = 6


# ==========================
# 🔹 INVENTORY ADMIN
# ==========================
@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "resource",
        "quantity",
        "batch_id",
        "source_warehouse",
        "added_by",
        "created_at",
    )
    list_filter = ("source_warehouse", "resource__category")
    search_fields = ("batch_id", "resource__name", "added_by__email")
    ordering = ("-created_at",)


# ==========================
# 🔹 DEPLOYMENT ADMIN
# ==========================
@admin.register(ResourceDeployment)
class ResourceDeploymentAdmin(OSMGeoAdmin):
    list_display = (
        "resource",
        "quantity",
        "deployment_status",
        "incident",
        "deployed_by",
        "deployed_at",
    )
    list_filter = ("deployment_status", "resource__category")
    search_fields = ("resource__name", "incident__description", "deployed_by__email")
    default_lon = 28.3
    default_lat = -15.4
    default_zoom = 6

    def colored_status(self, obj):
        colors = {
            "pending": "#f59e0b",
            "en_route": "#3b82f6",
            "delivered": "#16a34a",
            "cancelled": "#dc2626",
        }
        color = colors.get(obj.deployment_status, "#9ca3af")
        return format_html(
            f'<span style="color: {color}; font-weight: 600;">{obj.deployment_status.title()}</span>'
        )
    colored_status.short_description = "Status"


# ==========================
# 🔹 RESOURCE REQUEST ADMIN
# ==========================
@admin.register(ResourceRequest)
class ResourceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "resource",
        "quantity",
        "requester",
        "status_colored",
        "admin_note",
        "created_at",
    )
    list_filter = ("status", "resource__category")
    search_fields = ("requester__email", "resource__name", "reason")
    readonly_fields = ("created_at", "updated_at")

    def status_colored(self, obj):
        colors = {
            "Pending": "#f59e0b",
            "Approved": "#16a34a",
            "Denied": "#dc2626",
        }
        color = colors.get(obj.status, "#9ca3af")
        return format_html(f'<strong style="color:{color}">{obj.status}</strong>')
    status_colored.short_description = "Status"
