from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.gis.admin import OSMGeoAdmin
from django.utils.html import format_html

from .models import User


# ==========================
# 🔹 USER ADMIN
# ==========================
@admin.register(User)
class UserAdmin(OSMGeoAdmin, BaseUserAdmin):
    # Display fields in list view
    list_display = (
        "full_name",
        "email",
        "role_colored",
        "phone_number",
        "is_verified",
        "is_active",
        "created_at",
    )
    list_filter = ("role", "is_verified", "is_active", "is_staff", "created_at")
    search_fields = ("email", "first_name", "last_name", "phone_number")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "last_login")

    # Default map view center (Zambia)
    default_lon = 28.3
    default_lat = -15.4
    default_zoom = 6

    # Fields shown on the edit page
    fieldsets = (
        ("Personal Info", {
            "fields": ("first_name", "last_name", "email", "phone_number", "location")
        }),
        ("Role & Permissions", {
            "fields": ("role", "is_verified", "is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        ("Authentication", {"fields": ("password",)}),
        ("Timestamps", {"fields": ("last_login", "created_at")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "first_name",
                "last_name",
                "email",
                "phone_number",
                "password1",
                "password2",
                "role",
                "is_verified",
                "is_active",
            ),
        }),
    )

    # Custom methods for better visuals
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = "Name"

    def role_colored(self, obj):
        colors = {
            "Admin": "#16a34a",
            "Responder": "#3b82f6",
            "Citizen": "#f59e0b",
        }
        color = colors.get(obj.role, "#9ca3af")
        return format_html(f'<strong style="color:{color}">{obj.role}</strong>')
    role_colored.short_description = "Role"
