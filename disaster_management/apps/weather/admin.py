from django.contrib import admin
from django.contrib.gis.admin import OSMGeoAdmin
from django.utils.html import format_html

from .models import RiskZone, HistoricalIncident, WeatherLog, DataSource


# ==========================
# 🔹 RISK ZONE ADMIN
# ==========================
@admin.register(RiskZone)
class RiskZoneAdmin(OSMGeoAdmin):
    list_display = ("zone_name", "colored_risk", "calculated_at")
    list_filter = ("risk_level",)
    search_fields = ("zone_name",)
    ordering = ("-calculated_at",)

    # Default map view
    default_lon = 28.3
    default_lat = -15.4
    default_zoom = 6

    def colored_risk(self, obj):
        colors = {
            "low": "#22c55e",       # Green
            "medium": "#f59e0b",    # Amber
            "high": "#dc2626",      # Red
        }
        color = colors.get(obj.risk_level, "#9ca3af")
        return format_html(
            f'<strong style="color:{color};text-transform:capitalize;">{obj.risk_level}</strong>'
        )
    colored_risk.short_description = "Risk Level"


# ==========================
# 🔹 HISTORICAL INCIDENT ADMIN
# ==========================
@admin.register(HistoricalIncident)
class HistoricalIncidentAdmin(OSMGeoAdmin):
    list_display = ("incident_type", "description_short", "occurred_at")
    list_filter = ("incident_type",)
    search_fields = ("incident_type", "description")
    ordering = ("-occurred_at",)
    default_lon = 28.3
    default_lat = -15.4
    default_zoom = 6

    def description_short(self, obj):
        return (obj.description[:70] + "...") if len(obj.description) > 70 else obj.description
    description_short.short_description = "Description"


# ==========================
# 🔹 WEATHER LOG ADMIN
# ==========================
@admin.register(WeatherLog)
class WeatherLogAdmin(OSMGeoAdmin):
    list_display = (
        "city_name",
        "condition_colored",
        "temperature",
        "humidity",
        "wind_speed",
        "recorded_at",
    )
    list_filter = ("condition",)
    search_fields = ("city_name", "condition")
    ordering = ("-recorded_at",)
    default_lon = 28.3
    default_lat = -15.4
    default_zoom = 6

    def condition_colored(self, obj):
        color = (
            "#60a5fa" if "Rain" in obj.condition else
            "#16a34a" if "Clear" in obj.condition else
            "#f59e0b" if "Cloud" in obj.condition else
            "#dc2626" if "Storm" in obj.condition else
            "#9ca3af"
        )
        return format_html(f'<strong style="color:{color}">{obj.condition}</strong>')
    condition_colored.short_description = "Condition"


# ==========================
# 🔹 DATA SOURCE ADMIN
# ==========================
@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "base_url", "is_active_colored", "last_sync")
    list_filter = ("active",)
    search_fields = ("name", "base_url")
    readonly_fields = ("last_sync",)

    def is_active_colored(self, obj):
        color = "#16a34a" if obj.active else "#dc2626"
        return format_html(f'<strong style="color:{color}">{ "Active" if obj.active else "Inactive" }</strong>')
    is_active_colored.short_description = "Status"
