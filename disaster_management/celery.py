# disaster_management/celery.py
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "disaster_management.settings")

app = Celery("disaster_management")

# Read CELERY_* settings from Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Ensure schedules run in Zambia local time
app.conf.timezone = "Africa/Lusaka"
app.conf.enable_utc = False

# Discover tasks
app.autodiscover_tasks()

# NOTE: Task names below must match the registered names.
# With @shared_task in forecasting/tasks.py, the canonical name is:
#   "forecasting.tasks.<function_name>"
# Adjust if your app label/module differs.

app.conf.beat_schedule = {
    # ───────────────── Weather ingestion & base risk calc ─────────────────
    "fetch-zambia-weather-every-hour": {
        "task": "disaster_management.apps.weather.tasks.pull_weather_data",
        "schedule": crontab(minute=0, hour="*/1"),  # top of every hour
    },
    "calculate-risk-zones-every-hour": {
        "task": "disaster_management.apps.weather.tasks.calculate_risk_zones",
        "schedule": crontab(minute=15, hour="*/1"),  # HH:15 every hour
    },

    # ───────────────── Season-aware hazard forecasting (forecasting.tasks) ─────────────────
    "run-flood-forecast-every-3-hours": {
        "task": "forecasting.tasks.run_flood_prediction",
        "schedule": crontab(minute=0, hour="*/3"),  # HH:00 every 3 hours
    },
    "run-drought-forecast-every-6-hours": {
        "task": "forecasting.tasks.run_drought_prediction",
        "schedule": crontab(minute=0, hour="*/6"),  # HH:00 every 6 hours
    },
    "run-heat-wave-forecast-every-6-hours": {
        "task": "forecasting.tasks.run_heat_wave_forecast",
        "schedule": crontab(minute=30, hour="*/6"),  # HH:30 every 6 hours
    },
    "check-seasonal-rain-anomalies": {
        "task": "forecasting.tasks.run_seasonal_rain_check",
        "schedule": crontab(minute=45, hour="*/6"),  # HH:45 every 6 hours
    },
    "check-drought-anomaly-daily": {
        "task": "forecasting.tasks.run_dry_season_alerts",
        "schedule": crontab(minute=0, hour=6),  # 06:00 daily
    },

    # ───────────────── Monthly/seasonal outlooks ─────────────────
    "run-monthly-rainfall-forecast": {
        "task": "forecasting.tasks.run_monthly_rainfall_forecast",
        "schedule": crontab(minute=0, hour=4, day_of_month="28"),  # 28th @ 04:00
    },
    "run-seasonal-outlook-every-month": {
        "task": "forecasting.tasks.run_seasonal_outlook",
        "schedule": crontab(minute=0, hour=1, day_of_month="1"),  # 1st @ 01:00
    },
}
