from django.contrib import admin
from .models import Shelter, ShelterType
from django.contrib.gis.admin import OSMGeoAdmin
@admin.register(ShelterType)
class ShelterTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name")

@admin.register(Shelter)
class ShelterAdmin(OSMGeoAdmin, admin.ModelAdmin):
    list_display = ("name", "shelter_type", "capacity", "current_occupants", "is_active")
