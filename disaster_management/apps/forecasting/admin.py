from django.contrib import admin
from django.contrib.gis.admin import OSMGeoAdmin
from .models import ForecastModel, ForecastResult


@admin.register(ForecastModel)
class ForecastModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'model_type', 'version', 'created_at')
    list_filter = ('model_type', 'created_at')
    search_fields = ('name', 'description')


@admin.register(ForecastResult)
class ForecastResultAdmin(OSMGeoAdmin):  # Enables map for polygons
    list_display = ('model', 'forecast_date', 'risk_level', 'confidence', 'area_name', 'predicted_at')
    list_filter = ('risk_level', 'model__model_type', 'forecast_date')
    search_fields = ('area_name', 'details')
    ordering = ('-forecast_date',)
    default_lon = 27.8493  # Centered on Zambia
    default_lat = -13.1339
    default_zoom = 6
