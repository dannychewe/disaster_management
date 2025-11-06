from django.contrib import admin
from django.contrib.gis.admin import OSMGeoAdmin
from django.utils.html import format_html

from .models import IncidentType, Incident, IncidentMedia, IncidentComment


# ==========================
# 🔹 INCIDENT TYPE ADMIN
# ==========================
@admin.register(IncidentType)
class IncidentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)


# ==========================
# 🔹 INCIDENT MEDIA INLINE
# ==========================
class IncidentMediaInline(admin.TabularInline):
    model = IncidentMedia
    extra = 0
    readonly_fields = ("preview", "uploaded_at")

    def preview(self, obj):
        if obj.media_file:
            if str(obj.media_file).lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
                return format_html(f'<img src="{obj.media_file.url}" width="100" height="100" style="object-fit: cover; border-radius: 6px;" />')
            return format_html(f'<a href="{obj.media_file.url}" target="_blank">View File</a>')
        return "-"
    preview.short_description = "Preview"


# ==========================
# 🔹 INCIDENT COMMENT INLINE
# ==========================
class IncidentCommentInline(admin.TabularInline):
    model = IncidentComment
    extra = 0
    readonly_fields = ("user", "comment", "created_at")
    can_delete = False


# ==========================
# 🔹 INCIDENT ADMIN
# ==========================
@admin.register(Incident)
class IncidentAdmin(OSMGeoAdmin):
    list_display = (
        "id",
        "incident_type",
        "status_colored",
        "risk_score",
        "user",
        "assigned_responder",
        "reported_at",
        "updated_at",
    )
    list_filter = ("status", "incident_type", "reported_at")
    search_fields = (
        "description",
        "user__email",
        "assigned_responder__email",
        "incident_type__name",
    )
    ordering = ("-reported_at",)
    inlines = [IncidentMediaInline, IncidentCommentInline]
    readonly_fields = ("reported_at", "updated_at")

    # Default map position (Zambia region)
    default_lon = 28.3
    default_lat = -15.4
    default_zoom = 6

    def status_colored(self, obj):
        colors = {
            "pending": "#f59e0b",
            "responding": "#3b82f6",
            "resolved": "#16a34a",
        }
        color = colors.get(obj.status, "#9ca3af")
        return format_html(
            f'<strong style="color:{color}; text-transform:capitalize;">{obj.status}</strong>'
        )
    status_colored.short_description = "Status"
