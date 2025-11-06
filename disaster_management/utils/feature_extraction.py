# forecasts/utils/feature_extraction.py
import pandas as pd
from datetime import timedelta
from django.utils import timezone

from disaster_management.apps.weather.models import HistoricalIncident, WeatherLog
from disaster_management.utils.climate_constants import SEASON_CONFIG, _lusaka_month, _rain_indicator, _recent_rain_counts, _temp_anomaly, get_season

from django.contrib.gis.measure import D


# --------------- Flood features ----------------
def extract_flood_features() -> pd.DataFrame:
    """
    Season-aware features for flood prediction.
    Adds:
      - season label & multipliers
      - rainfall_recent_24h / 72h counts (localized)
      - temperature anomaly vs monthly baseline
      - flood_history within 5km
    """
    now = timezone.now()
    month = _lusaka_month(now)  # use Africa/Lusaka
    season = get_season(month)
    weights = SEASON_CONFIG[season]

    past_24h = now - timedelta(hours=24)

    # Precompute localized rainfall counts for 24h and 72h
    rain24 = _recent_rain_counts(now, window_hours=24)
    rain72 = _recent_rain_counts(now, window_hours=72)

    logs = (
        WeatherLog.objects
        .filter(recorded_at__gte=past_24h)
        .only("location", "condition", "temperature", "humidity", "wind_speed", "recorded_at")
    )

    rows = []
    for log in logs:
        if not getattr(log, "location", None):
            continue

        # localized bucket
        lat2 = round(log.location.y, 2)
        lon2 = round(log.location.x, 2)
        key = (lat2, lon2)

        flood_history_exists = HistoricalIncident.objects.filter(
            incident_type__icontains="flood",
            location__distance_lte=(log.location, D(m=5000)),
        ).exists()

        rain_flag = _rain_indicator(log)
        temp_anom = _temp_anomaly(getattr(log, "temperature", None), month)

        # Season-aware engineered features
        rainfall_recent_24h = rain24.get(key, 0)
        rainfall_recent_72h = rain72.get(key, 0)

        rows.append({
            # raw weather
            "temperature": log.temperature,
            "humidity": log.humidity,
            "wind_speed": log.wind_speed,
            "rain_flag": rain_flag,

            # engineered
            "temp_anomaly": temp_anom,
            "rainfall_recent_24h": rainfall_recent_24h,
            "rainfall_recent_72h": rainfall_recent_72h,
            "flood_history": 1 if flood_history_exists else 0,

            # season signals
            "season": season,
            "flood_season_mult": weights.flood_mult,

            # context
            "location": log.location,
            "timestamp": log.recorded_at,
        })

    return pd.DataFrame(rows)



# --------------- Drought features ----------------
def extract_drought_features() -> pd.DataFrame:
    """
    Season-aware aggregation for drought assessment.
    Adds:
      - season label & multipliers
      - 7-day rain count vs expected per season (rain_deficit)
      - mean temp/humidity, temp anomaly
      - representative point per ~0.1° grid cell
    """
    now = timezone.now()
    past_7_days = now - timedelta(days=7)

    logs = (
        WeatherLog.objects
        .filter(recorded_at__gte=past_7_days)
        .only("location", "condition", "temperature", "humidity", "recorded_at")
    )

    # No data
    if not logs:
        return pd.DataFrame()

    # Determine the most frequent Lusaka-local month across the 7-day window
    months = [_lusaka_month(log.recorded_at) for log in logs if getattr(log, "recorded_at", None)]
    month = max(set(months), key=months.count) if months else _lusaka_month(now)
    season = get_season(month)
    weights = SEASON_CONFIG[season]

    # Accumulate per ~region (0.1° grid)
    data = []
    for log in logs:
        if not getattr(log, "location", None):
            continue
        lat = round(log.location.y, 1)
        lon = round(log.location.x, 1)
        rain = _rain_indicator(log)
        data.append({
            "lat": lat,
            "lon": lon,
            "temperature": log.temperature,
            "humidity": log.humidity,
            "rain": rain,
            "temp_anomaly": _temp_anomaly(getattr(log, "temperature", None), month),
            "location": log.location,
        })

    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame()

    grouped = df.groupby(["lat", "lon"]).agg({
        "temperature": "mean",
        "humidity": "mean",
        "rain": "sum",
        "temp_anomaly": "mean",
        "location": "first",  # representative point
    }).reset_index()

    # Season-aware drought features
    grouped["season"] = season
    grouped["expected_rain_days_last7"] = weights.expected_rain_days_last7
    grouped["rain_deficit"] = (grouped["expected_rain_days_last7"] - grouped["rain"]).clip(lower=0)
    grouped["drought_season_mult"] = weights.drought_mult

    return grouped