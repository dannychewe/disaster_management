from celery import shared_task
import time
import logging
import requests
from django.utils import timezone
from django.contrib.gis.geos import Point, GEOSGeometry

from disaster_management.utils.climate_constants import ZAMBIA_COORDINATES, _lusaka_month, get_season
from disaster_management.utils.notifications import send_alert
from .models import RiskZone, WeatherLog, DataSource
from datetime import timedelta
from datetime import datetime, timedelta, timezone as dt_timezone
from math import cos, radians
log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15  # seconds
MAX_RETRIES = 3
BACKOFF_SECS = [1, 3, 6]  # simple linear-ish backoff


def _normalize_condition(main: str | None, description: str | None, rainfall_mm: float) -> str:
    """
    Map OpenWeather 'weather.main'/'description' to our canonical set used by risk features:
      {'rain', 'storm', 'thunderstorm', 'showers', 'clear', 'clouds', ...}
    """
    m = (main or "").strip().lower()
    d = (description or "").strip().lower()

    if rainfall_mm > 0:
        # prioritize explicit rain
        if "thunder" in d or m == "thunderstorm":
            return "thunderstorm"
        if "shower" in d:
            return "showers"
        return "rain"

    if m in {"thunderstorm"} or "thunder" in d:
        return "thunderstorm"
    if m in {"drizzle"} or "shower" in d:
        return "showers"
    if m in {"rain"}:
        return "rain"
    if m in {"clear"}:
        return "clear"
    if m in {"clouds"}:
        return "clouds"
    return m or "unknown"


def _fetch_weather(session: requests.Session, lat: float, lon: float, api_key: str) -> dict:
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
    resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@shared_task
def pull_weather_data() -> str:
    try:
        source = DataSource.objects.get(name="OpenWeatherMap", active=True)
    except DataSource.DoesNotExist:
        send_alert(
            title="❌ Weather Sync Failed",
            message="No active OpenWeatherMap data source found. Weather logs could not be updated.",
            severity="critical",
        )
        return "No active weather source found."

    session = requests.Session()
    success = 0
    created_objects: list[WeatherLog] = []

    # Detect optional model fields once (avoids kwargs errors if field absent)
    weatherlog_fields = {f.name for f in WeatherLog._meta.get_fields()}
    supports_rainfall = "rainfall_mm" in weatherlog_fields
    supports_pressure = "pressure" in weatherlog_fields
    supports_clouds = "clouds" in weatherlog_fields
    supports_visibility = "visibility" in weatherlog_fields
    supports_source = "source" in weatherlog_fields  # if you store provenance

    for loc in ZAMBIA_COORDINATES:
        city = loc["city"]
        lat = float(loc["lat"])
        lon = float(loc["lon"])

        data = None
        for attempt in range(MAX_RETRIES):
            try:
                data = _fetch_weather(session, lat, lon, source.api_key)
                break
            except requests.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_SECS[attempt])
                    continue
                log.warning("[weather] %s: request failed after retries: %s", city, e)

        if not data:
            continue

        try:
            main = data.get("main", {})
            wind = data.get("wind", {})
            wx = (data.get("weather") or [{}])[0]
            clouds = (data.get("clouds") or {}).get("all")
            visibility = data.get("visibility")

            temp = main.get("temp")
            humidity = main.get("humidity")
            wind_speed = wind.get("speed")
            condition_main = wx.get("main")
            description = wx.get("description")
            rain_1h = (data.get("rain") or {}).get("1h")
            rain_3h = (data.get("rain") or {}).get("3h")
            rainfall_mm = float(rain_1h if rain_1h is not None else (rain_3h / 3.0 if rain_3h else 0.0))

            # robust check for completeness
            if temp is None or humidity is None or wind_speed is None:
                log.info("[weather] Skipping %s — incomplete weather data.", city)
                continue

            # Normalize to our canonical condition labels
            condition = _normalize_condition(condition_main, description, rainfall_mm)

            # Use provider timestamp if available; fall back to now()
            dt_unix = data.get("dt")
            if isinstance(dt_unix, (int, float)):
                recorded_at = datetime.fromtimestamp(int(dt_unix), tz=dt_timezone.utc)
            else:
                recorded_at = timezone.now()

            kwargs = dict(
                temperature=float(temp),
                humidity=float(humidity),
                wind_speed=float(wind_speed),
                condition=condition,
                location=Point(lon, lat, srid=4326),
                city_name=city,
                recorded_at=recorded_at,
            )
            if supports_rainfall:
                kwargs["rainfall_mm"] = rainfall_mm
            if supports_pressure and main.get("pressure") is not None:
                kwargs["pressure"] = float(main["pressure"])
            if supports_clouds and clouds is not None:
                kwargs["clouds"] = float(clouds)
            if supports_visibility and visibility is not None:
                kwargs["visibility"] = float(visibility)
            if supports_source:
                kwargs["source"] = "OpenWeatherMap"

            created_objects.append(WeatherLog(**kwargs))
            success += 1
            log.debug("[weather] Prepared log for %s", city)

        except Exception as e:
            log.exception("[weather] Error processing %s: %s", city, e)
            continue

    # Bulk write
    if created_objects:
        WeatherLog.objects.bulk_create(created_objects, batch_size=200)
        log.info("[weather] Saved %d weather logs.", len(created_objects))
    else:
        send_alert(
            title="⚠️ Weather Sync Failed",
            message="All weather data fetch attempts failed. No weather logs were saved.",
            severity="warning",
        )

    # Update data source sync time
    source.last_sync = timezone.now()
    source.save(update_fields=["last_sync"])

    return f"Weather logs updated for {success} cities."



def _degree_buffer_for_meters(lat_deg: float, meters: float) -> float:
    """Approximate a degree radius that corresponds to ~meters at latitude lat_deg."""
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = m_per_deg_lat * max(0.1, cos(radians(lat_deg)))
    deg_lat = meters / m_per_deg_lat
    deg_lon = meters / m_per_deg_lon
    return float(min(deg_lat, deg_lon))


def _determine_risk(log, season: str) -> str:
    """
    Season-aware but conservative risk heuristic.
    Keeps your original thresholds and adds a storm/wind trigger.
    """
    temp = (log.temperature or 0)
    hum = (log.humidity or 0)
    wind = (log.wind_speed or 0)
    cond = ((log.condition or "").strip().lower())

    # Extra high-risk trigger for severe convection in the rainy season
    stormy = cond in {"storm", "thunderstorm"} or "thunder" in cond

    if (temp > 35 and hum > 70 and wind > 10) or (stormy and wind >= 8):
        return "high"
    if (temp > 30 and hum > 50 and wind > 5) or (cond in {"rain", "showers"} and wind >= 6):
        return "medium"
    return "low"


@shared_task
def calculate_risk_zones() -> str:
    """
    Compute/refresh short-lived risk zones from the last 2 hours of WeatherLog points.
    Creates/updates one RiskZone per ~point cell (named by rounded lon/lat).
    Sends alerts for HIGH risk zones.
    """
    now = timezone.now()
    window_start = now - timedelta(hours=2)

    logs = (
        WeatherLog.objects
        .filter(recorded_at__gte=window_start)
        .only("location", "temperature", "humidity", "wind_speed", "condition", "city_name", "recorded_at")
    )

    if not logs.exists():
        return "No recent weather logs to compute risk zones."

    created = 0
    high_risk_alerts = 0

    # Lusaka-local season (for optional tweaks in _determine_risk)
    season = get_season(_lusaka_month(now))

    for log in logs:
        point = getattr(log, "location", None)
        if point is None:
            continue

        # Determine risk level
        risk_level = _determine_risk(log, season)

        # Build a ~4 km footprint around the observation point (no GDAL required)
        try:
            lon = float(point.x)
            lat = float(point.y)
        except Exception:
            continue

        deg_radius = _degree_buffer_for_meters(lat, meters=4_000.0)
        try:
            polygon = point.buffer(deg_radius)
        except Exception:
            # conservative fallback if GEOS buffer fails
            polygon = point.buffer(0.036)

        if not polygon or polygon.empty:
            continue

        # Stable, human-readable zone name based on rounded coords
        zone_name = f"Zone near ({lon:.2f}, {lat:.2f})"

        zone, was_created = RiskZone.objects.update_or_create(
            zone_name=zone_name,
            defaults={
                "geometry": polygon,
                "risk_level": risk_level,
                "calculated_at": timezone.localtime(now),
            },
        )

        if was_created:
            created += 1

        # 🔔 Alert on high risk
        if risk_level == "high":
            high_risk_alerts += 1
            city = (log.city_name or f"{lon:.2f},{lat:.2f}")
            send_alert(
                title="🚨 High-Risk Weather Zone Detected",
                message=(
                    f"High-risk weather zone near {city}. "
                    f"Conditions: Temp={log.temperature}, Humidity={log.humidity}, Wind={log.wind_speed}."
                ),
                severity="critical",
            )

    return f"Calculated risk zones: {created} new/updated, {high_risk_alerts} high-risk alerts triggered."