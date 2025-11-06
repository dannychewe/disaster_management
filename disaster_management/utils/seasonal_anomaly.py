from datetime import timedelta
from django.utils import timezone

from disaster_management.apps.weather.models import WeatherLog
from disaster_management.utils.climate_constants import (
    SEASON_CONFIG, get_season, _rain_indicator
)

def detect_drought_anomaly(city_name: str):
    """
    Flag drought-like anomaly if the last 14 days in a city have
    fewer rainy days than expected for the season.
    Only alerts during the rainy season.
    """
    now = timezone.now()
    local_month = timezone.localtime(now).month
    season = get_season(local_month)

    # Only consider anomalies during the rainy season
    if season != "rainy":
        return None

    past_14_days = now - timedelta(days=14)

    # Pull minimal fields, guard against big payloads
    logs = (
        WeatherLog.objects
        .filter(city_name__iexact=city_name, recorded_at__gte=past_14_days)
        .only("recorded_at", "condition", "rainfall_mm")  # rainfall_mm if you have it
    )

    if not logs:
        # No data; you can return a low-confidence warning or None
        return {
            "city": city_name,
            "rain_days": 0,
            "risk_level": "unknown",
            "message": f"No weather data for {city_name} in the past 14 days."
        }

    # Count distinct local dates with rain
    rainy_dates = set()
    for log in logs:
        # Prefer numeric rainfall if available; fall back to condition text
        has_rain = (getattr(log, "rainfall_mm", None) or 0) > 0 or _rain_indicator(log) == 1
        if has_rain and getattr(log, "recorded_at", None):
            rainy_dates.add(timezone.localtime(log.recorded_at).date())

    rain_days = len(rainy_dates)

    # Expectation for rainy season: 3 rainy days / 7  → about 6 / 14
    expected_14 = SEASON_CONFIG["rainy"].expected_rain_days_last7 * 2  # ≈ 6
    # Add a small tolerance so we don’t over-alert
    threshold = max(0, expected_14 - 1)

    if rain_days < threshold:
        return {
            "city": city_name,
            "rain_days": rain_days,
            "risk_level": "high",
            "message": (
                f"Low rainfall in {city_name} during rainy season: "
                f"only {rain_days} rainy day(s) in the last 14 days (expected ≥ {threshold})."
            ),
            "window_days": 14,
            "season": season,
        }

    return None
