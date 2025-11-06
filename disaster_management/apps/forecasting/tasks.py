# forecasts/tasks.py
from celery import shared_task
from django.utils.timezone import now, timezone
from typing import Dict, List, Tuple
from disaster_management.apps.forecasting.models import ForecastModel, ForecastResult
from disaster_management.apps.notifications.models import Notification
from disaster_management.apps.weather.models import WeatherLog
from disaster_management.models.dummy_flood_predictor import predict
from disaster_management.utils.climate_constants import MONTHLY_TEMP_BASELINE, RAINY_SEASON_MONTHS, SEASON_CONFIG, ZAMBIA_CITIES, _lusaka_month, _temp_anomaly, get_season
from disaster_management.utils.feature_extraction import extract_drought_features, extract_flood_features
from django.utils.timezone import now, timedelta
from django.contrib.gis.geos import Point
from disaster_management.utils.monthly_rainfall_dataset import build_rainfall_training_set
from disaster_management.utils.notifications import send_alert, send_seasonal_alert_email
from disaster_management.utils.risk_scoring import score_drought_df, score_flood_df
from disaster_management.utils.seasonal_anomaly import detect_drought_anomaly
from disaster_management.utils.seasonal_rainfall import get_monthly_rainfall_history
import pandas as pd
from django.utils.timezone import now
from disaster_management.apps.weather.models import WeatherLog
from disaster_management.apps.forecasting.models import ForecastModel, ForecastResult
import joblib
from math import cos, radians
from django.db.models import Q, Count
from django.db.models.functions import TruncDate, ExtractMonth
from django.db import transaction
# --- helpers ---------------------------------------------------------------

def _risk_bucket(score: float) -> tuple[str, float]:
    """
    Map a 0..1 score to ('low'|'medium'|'high', confidence).
    Confidence is the score itself (you can refine later).
    """
    if score >= 0.70:
        return "high", float(score)
    if score >= 0.40:
        return "medium", float(score)
    return "low", float(score)


def _degree_buffer_for_meters(lat_deg: float, meters: float) -> float:
    """
    Approximate a degree radius on WGS84 to get about `meters` radius on Earth.
    Uses latitude to adjust longitudinal scale. We return a single degree radius
    for GEOS buffer on geographic coords (planar in degrees).
    """
    # ~111.32 km per degree latitude; longitude shrinks by cos(latitude)
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = meters_per_deg_lat * max(0.1, cos(radians(lat_deg)))  # guard near poles

    deg_lat = meters / meters_per_deg_lat
    deg_lon = meters / meters_per_deg_lon
    # GEOS buffer on geographic coords is isotropic in degrees;
    # use the smaller to avoid over-inflating areas east-west.
    return float(min(deg_lat, deg_lon))


def _risk_from_anomaly(avg_anom: float, season: str) -> tuple[str, float]:
    """
    Map average temp anomaly (°C) to risk bucket + confidence.
    Baselines: high >= +5°C, medium >= +3°C.
    Season shift: hot_dry (+1°C), cool_dry (-0.5°C), rainy (0).
    """
    shift = 0.0
    if season == "hot_dry":
        shift = +1.0
    elif season == "cool_dry":
        shift = -0.5
    # thresholds after shift
    high_th = 5.0 + shift
    med_th  = 3.0 + shift

    if avg_anom >= high_th:
        return "high", float(min(1.0, 0.6 + (avg_anom - high_th) / 6.0))
    if avg_anom >= med_th:
        return "medium", float(min(0.9, 0.45 + (avg_anom - med_th) / 6.0))
    return "low", float(max(0.1, 0.2 + avg_anom / 12.0))



def _degree_buffer_for_meters(lat_deg: float, meters: float) -> float:
    """Approximate degree radius for ~meters on WGS84 (no GDAL required)."""
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = meters_per_deg_lat * max(0.1, cos(radians(lat_deg)))
    deg_lat = meters / meters_per_deg_lat
    deg_lon = meters / meters_per_deg_lon
    return float(min(deg_lat, deg_lon))

def _next_month(dt) -> int:
    local = timezone.localtime(dt)
    m = local.month
    return 1 if m == 12 else (m + 1)

def _risk_from_expected(avg_days: float, season: str) -> tuple[str, float, int]:
    """
    Compare avg rainy days vs season baseline for a month.
    Baseline = expected_rain_days_last7 * ~4 weeks  (e.g., rainy: 3*4 = 12).
    - high   if < 50% of baseline
    - medium if < 80% of baseline
    - low    otherwise
    Confidence is proportional to distance from the medium threshold.
    Returns (risk_level, confidence, baseline_days)
    """
    expected_week = SEASON_CONFIG[season].expected_rain_days_last7
    baseline = int(round(expected_week * 4))  # month-level expectation
    # guard to avoid divide-by-zero (hot_dry can be 0)
    if baseline <= 0:
        # In non-rainy months baseline may be 0 → treat deficits as low risk
        return "low", 0.5, baseline

    ratio = avg_days / float(baseline)

    if ratio < 0.50:
        # farther below → higher confidence, cap at 1.0
        conf = min(1.0, 0.7 + (0.50 - ratio) * 0.6)
        return "high", conf, baseline
    if ratio < 0.80:
        conf = min(0.9, 0.5 + (0.80 - ratio) * 0.6)
        return "medium", conf, baseline
    return "low", 0.6, baseline


def _current_rainy_window(now):
    """
    Return (start_dt, end_dt) for the *current* rainy season window in Africa/Lusaka.
    Zambia rainy season ≈ Nov–Apr, spanning years.
    """
    local = timezone.localtime(now)
    year = local.year
    month = local.month
    tz = timezone.get_current_timezone()

    if month >= 11:  # Nov–Dec → window: Nov (this year) to Apr (next year)
        start = timezone.make_aware(timezone.datetime(year, 11, 1, 0, 0, 0), tz)
        end   = timezone.make_aware(timezone.datetime(year + 1, 4, 30, 23, 59, 59), tz)
    else:
        # Jan–Oct → window: Nov (last year) to Apr (this year)
        start = timezone.make_aware(timezone.datetime(year - 1, 11, 1, 0, 0, 0), tz)
        end   = timezone.make_aware(timezone.datetime(year, 4, 30, 23, 59, 59), tz)
    return start, end

def _city_coord_map() -> Dict[str, Tuple[float, float]]:
    # ZAMBIA_CITIES is [("Lusaka", lon, lat), ...]
    return {name: (lon, lat) for (name, lon, lat) in ZAMBIA_CITIES}

FEATURE_MONTHS = [12, 1, 2, 3]

def _label_to_risk(label: str) -> str:
    # keep your mapping
    if label == "failed":
        return "high"
    if label == "delayed":
        return "medium"
    return "low"

# --- task ------------------------------------------------------------------

@shared_task
def run_flood_prediction() -> str:
    # 1) Load or create the model metadata
    model, _ = ForecastModel.objects.get_or_create(
        name="Season-Aware Flood Predictor",
        model_type="flood",
        defaults={"description": "Season-aware rule/score-based flood predictor using rainfall, anomalies, and history."},
    )

    # 2) Extract features and score
    features_df = extract_flood_features()
    if features_df.empty:
        return "No flood features available."

    scored_df = score_flood_df(features_df)
    if "flood_risk" not in scored_df.columns:
        return "Scoring failed: missing 'flood_risk'."

    # 3) Build ForecastResult rows
    lusaka_now = timezone.localtime(timezone.now())
    forecast_date = lusaka_now.date()

    results_to_create = []
    alerts_to_send = []

    for _, row in scored_df.iterrows():
        point = row.get("location")
        if point is None:
            continue

        # Area name
        try:
            lon = float(point.x)
            lat = float(point.y)
        except Exception:
            # Fallback if geometry is unexpected
            continue

        area_name = f"Flood Zone near {lon:.3f}, {lat:.3f}"

        # Polygon buffer (~3 km radius) without requiring GDAL/transform
        deg_radius = _degree_buffer_for_meters(lat, meters=3_000.0)
        try:
            polygon = point.buffer(deg_radius)
        except Exception:
            # As a last resort, keep a tiny buffer
            polygon = point.buffer(0.01)

        score = float(row["flood_risk"])
        risk_level, confidence = _risk_bucket(score)

        details = (
            f"season={row.get('season')}, mult={row.get('flood_season_mult')}, "
            f"rain24={row.get('rainfall_recent_24h')}, rain72={row.get('rainfall_recent_72h')}, "
            f"rain_flag={row.get('rain_flag')}, temp_anom={row.get('temp_anomaly')}, "
            f"history={row.get('flood_history')}, ts={row.get('timestamp')}"
        )

        results_to_create.append(
            ForecastResult(
                model=model,
                forecast_date=forecast_date,
                predicted_at=lusaka_now,
                affected_area=polygon,
                area_name=area_name,
                risk_level=risk_level,
                confidence=confidence,
                details=details,
            )
        )

        # Queue high-risk alerts for later send
        if risk_level == "high" and confidence >= 0.75:
            alerts_to_send.append((area_name, confidence))

    # 4) Persist in bulk
    if results_to_create:
        ForecastResult.objects.bulk_create(results_to_create, batch_size=500)

    # 5) Fire alerts (keep separate from DB write)
    for area_name, confidence in alerts_to_send:
        send_alert(
            title=f"🌊 Flood Risk Detected - {area_name}",
            message=(
                f"A flood risk has been detected with high confidence at {area_name}. "
                f"Confidence: {confidence * 100:.1f}%"
            ),
            severity="critical",
        )

    return f"{len(results_to_create)} flood forecasts saved; {len(alerts_to_send)} high-risk alerts sent."

@shared_task
def run_drought_prediction() -> str:
    # 1) Model metadata
    model, _ = ForecastModel.objects.get_or_create(
        name="Season-Aware Drought Predictor",
        model_type="drought",
        defaults={"description": "Season-aware score-based drought predictor using rain deficit, temp, humidity, anomalies."},
    )

    # 2) Feature extraction & scoring
    features_df = extract_drought_features()
    if features_df.empty:
        return "No recent data for drought prediction."

    scored_df = score_drought_df(features_df)
    if "drought_risk" not in scored_df.columns:
        return "Scoring failed: missing 'drought_risk'."

    # 3) Persist results (bulk), send alerts for high risk
    lusaka_now = timezone.localtime(timezone.now())
    forecast_date = lusaka_now.date()

    to_create = []
    to_alert = []

    # Use a slightly larger footprint for drought (~5 km)
    default_buffer_m = 5_000.0

    for _, row in scored_df.iterrows():
        point = row.get("location")
        if point is None:
            continue

        # Lat/Lon & area name
        try:
            lon = float(point.x)
            lat = float(point.y)
        except Exception:
            continue

        area_name = f"Drought Zone near {lon:.3f}, {lat:.3f}"

        # Build a polygon buffer without metric transform
        deg_radius = _degree_buffer_for_meters(lat, meters=default_buffer_m)
        try:
            polygon = point.buffer(deg_radius)
        except Exception:
            polygon = point.buffer(0.02)  # conservative fallback

        score = float(row["drought_risk"])
        risk_level, confidence = _risk_bucket(score)

        # Human-readable detail string (safe .get() lookups)
        details = (
            f"season={row.get('season')}, mult={row.get('drought_season_mult')}, "
            f"rain_deficit={row.get('rain_deficit')}, "
            f"temp={row.get('temperature')}, humid={row.get('humidity')}, "
            f"temp_anom={row.get('temp_anomaly')}"
        )

        to_create.append(
            ForecastResult(
                model=model,
                forecast_date=forecast_date,
                predicted_at=lusaka_now,
                affected_area=polygon,
                area_name=area_name,
                risk_level=risk_level,
                confidence=confidence,
                details=details,
            )
        )

        if risk_level == "high" and confidence >= 0.75:
            to_alert.append((area_name, confidence))

    if to_create:
        ForecastResult.objects.bulk_create(to_create, batch_size=500)

    for area_name, confidence in to_alert:
        send_alert(
            title=f"🌵 Drought Risk Alert - {area_name}",
            message=(
                f"Severe drought conditions predicted in {area_name}. "
                f"Confidence: {confidence * 100:.1f}%"
            ),
            severity="critical",
        )

    return f"{len(to_create)} drought forecasts saved; {len(to_alert)} high-risk alerts sent."

@shared_task
def run_heat_wave_forecast() -> str:
    """
    Detect heat-wave risk per city over the last 3 days using temperature anomalies
    vs MONTHLY_TEMP_BASELINE (by local month per log). Season-aware thresholds.
    """
    model, _ = ForecastModel.objects.get_or_create(
        name="Heat Wave Detector",
        model_type="heat_wave",
        defaults={"description": "Detects abnormal heat spikes vs climate norms (season-aware)."},
    )

    now = timezone.now()
    lusaka_now = timezone.localtime(now)
    recent = now - timezone.timedelta(days=3)

    # Pull only what we need
    qs = (
        WeatherLog.objects
        .filter(recorded_at__gte=recent)
        .only("city_name", "location", "temperature", "recorded_at")
    )

    # Aggregate in Python (window is small); compute anomaly per log using *local* month
    per_city = {}  # city -> dict(temps, anoms, locs, months)
    for log in qs:
        if log.temperature is None or not getattr(log, "location", None):
            continue
        city = (log.city_name or "").strip() or "Unknown"
        local_month = _lusaka_month(log.recorded_at)
        anom = _temp_anomaly(log.temperature, local_month)

        bucket = per_city.setdefault(city, {"temps": [], "anoms": [], "loc": None, "months": []})
        bucket["temps"].append(float(log.temperature))
        bucket["anoms"].append(float(anom))
        bucket["months"].append(local_month)
        # pick the first valid location as representative
        if bucket["loc"] is None:
            bucket["loc"] = log.location

    if not per_city:
        return "No recent data for heat-wave prediction."

    to_create = []
    alerts = 0

    for city, info in per_city.items():
        if not info["temps"]:
            continue

        avg_temp = sum(info["temps"]) / len(info["temps"])
        avg_anom = sum(info["anoms"]) / len(info["anoms"])

        # Determine the dominant season across the 3-day window
        if info["months"]:
            dom_month = max(set(info["months"]), key=info["months"].count)
        else:
            dom_month = _lusaka_month(lusaka_now)
        season = get_season(dom_month)

        risk_level, confidence = _risk_from_anomaly(avg_anom, season)

        # Skip low/no risk
        if risk_level == "low":
            continue

        point = info["loc"]
        try:
            lon, lat = float(point.x), float(point.y)
        except Exception:
            continue

        # Use a broader footprint for heat waves (~10 km)
        deg_radius = _degree_buffer_for_meters(lat, meters=10_000.0)
        try:
            polygon = point.buffer(deg_radius)
        except Exception:
            polygon = point.buffer(0.05)

        # For messaging, also show current month baseline
        month_baseline = MONTHLY_TEMP_BASELINE.get(dom_month, 28)

        details = (
            f"season={season}, avg_temp={avg_temp:.1f}°C, avg_anom={avg_anom:.1f}°C, "
            f"baseline_month={month_baseline}°C, samples={len(info['temps'])}"
        )

        to_create.append(
            ForecastResult(
                model=model,
                forecast_date=lusaka_now.date(),
                predicted_at=lusaka_now,
                affected_area=polygon,
                area_name=city,
                risk_level=risk_level,
                confidence=confidence,
                details=details,
            )
        )

    # Persist results
    if to_create:
        ForecastResult.objects.bulk_create(to_create, batch_size=200)

    # Alerts (only for high risk, >= 0.75 confidence)
    for res in to_create:
        if res.risk_level == "high" and res.confidence >= 0.75:
            send_alert(
                title=f"🔥 Heatwave Alert - {res.area_name}",
                message=(
                    f"Abnormally high temperatures detected in {res.area_name}. "
                    f"Confidence: {res.confidence * 100:.1f}%"
                ),
                severity="critical",
            )
            alerts += 1

    return f"{len(per_city)} cities checked; {len(to_create)} heat-wave forecasts saved; {alerts} alerts sent."


@shared_task
def run_seasonal_rain_check() -> str:
    """
    During the rainy season, flag cities with too few DISTINCT rainy days in the past 14 days.
    - Uses Africa/Lusaka local dates (TruncDate with tz).
    - "Rainy" prefers rainfall_mm > 0 if available; otherwise falls back to condition text.
    - Threshold is season-aware: expected_rain_days_last7 * 2 (≈ 6 in rainy season), minus a small tolerance.
    """
    now = timezone.now()
    lusaka_now = timezone.localtime(now)
    month = _lusaka_month(now)
    season = get_season(month)

    # Only run during rainy season
    if season != "rainy":
        return "Not rainy season — skipping anomaly check."

    # Model metadata
    model, _ = ForecastModel.objects.get_or_create(
        name="Rainy Season Monitor",
        model_type="drought",
        defaults={"description": "Checks for delayed or missing rains during rainy season"},
    )

    # Window & timezone for date bucketing
    past_14_days = now - timezone.timedelta(days=14)
    tz = timezone.get_current_timezone()

    # Base queryset for last 14 days, minimal columns
    base_qs = (
        WeatherLog.objects
        .filter(recorded_at__gte=past_14_days)
        .only("city_name", "location", "recorded_at", "condition", "rainfall_mm")
        .exclude(city_name__isnull=True)
        .exclude(city_name__exact="")
    )

    # If no data, exit early
    if not base_qs.exists():
        return "No logs in the last 14 days — nothing to check."

    # Define "rainy" condition
    rain_q = Q(condition__iregex=r"(rain|storm|showers|thunder)")
    try:
        rain_q = rain_q | Q(rainfall_mm__gt=0)
    except Exception:
        pass

    # DISTINCT rainy days per city in the last 14 days
    rainy_per_city = (
        base_qs.filter(rain_q)
        .annotate(date_local=TruncDate("recorded_at", tzinfo=tz))
        .values("city_name")
        .annotate(rain_days=Count("date_local", distinct=True))
    )
    rainy_map = {row["city_name"]: int(row["rain_days"]) for row in rainy_per_city}

    # Latest log per city (to get a representative point/extent)
    latest_per_city = (
        base_qs
        .order_by("city_name", "-recorded_at")
        .distinct("city_name")
        .values("city_name", "location", "recorded_at")
    )

    if not latest_per_city:
        return "No recent city observations — nothing to check."

    # Season-aware threshold (≈ 6 in rainy season) with a small tolerance
    expected_14 = SEASON_CONFIG["rainy"].expected_rain_days_last7 * 2  # 3*2 = 6
    threshold = max(0, expected_14 - 1)  # tolerance of 1 day

    to_create: list[ForecastResult] = []
    alerts_created = 0

    for row in latest_per_city:
        city = row["city_name"]
        point = row["location"]
        rain_days = rainy_map.get(city, 0)

        if point is None:
            continue  # skip malformed geometry

        # Only create a result when below threshold
        if rain_days < threshold:
            try:
                lon = float(point.x)
                lat = float(point.y)
            except Exception:
                continue

            # ~8 km footprint for city-wide advisory
            deg_radius = _degree_buffer_for_meters(lat, meters=8_000.0)
            try:
                polygon = point.buffer(deg_radius)
            except Exception:
                polygon = point.buffer(0.04)

            details = (
                f"season=rainy, window_days=14, rainy_days={rain_days}, "
                f"threshold={threshold}, last_obs={row.get('recorded_at')}"
            )

            to_create.append(
                ForecastResult(
                    model=model,
                    forecast_date=lusaka_now.date(),
                    predicted_at=lusaka_now,
                    affected_area=polygon,
                    area_name=city,
                    risk_level="high",
                    confidence=0.9,
                    details=details,
                )
            )

    # Persist all results
    if to_create:
        ForecastResult.objects.bulk_create(to_create, batch_size=200)

        # Fire alerts (critical) for each created result
        for res in to_create:
            send_alert(
                title=f"🌧️ Drought Warning: {res.area_name}",
                message=(
                    f"Low rainfall in {res.area_name} — only {res.details.split('rainy_days=')[1].split(',')[0]} "
                    f"rainy days in the past 2 weeks."
                ),
                severity="critical",
            )
            alerts_created += 1

    return f"{len(to_create)} rain anomaly alerts created."



@shared_task
def run_monthly_rainfall_forecast() -> str:
    """
    Forecast next month's rainfall *days* per city using historical monthly averages.
    - Uses Africa/Lusaka time to pick the next calendar month.
    - Season-aware thresholds derived from SEASON_CONFIG for that next month.
    - Persists results with bulk_create and sends alerts for MEDIUM/HIGH risk.
    """
    model, _ = ForecastModel.objects.get_or_create(
        name="Monthly Rainfall Trend Forecast",
        model_type="drought",
        defaults={"description": "Forecasts rainfall days for next month using seasonal historical trends."},
    )

    now = timezone.now()
    next_m = _next_month(now)
    season_next = get_season(next_m)

    results: List[ForecastResult] = []
    to_alert: list[tuple[str, str, float]] = []  # (city, risk, confidence)

    for city, lon, lat in ZAMBIA_CITIES:
        # Historical average rainy *days* for this city/month over past X years
        avg_rain_days = get_monthly_rainfall_history(city, next_m)
        if avg_rain_days is None:
            continue

        risk_level, confidence, baseline = _risk_from_expected(avg_rain_days, season_next)

        # Build a ~10 km footprint around the city point
        deg_radius = _degree_buffer_for_meters(lat, meters=10_000.0)
        polygon = Point(lon, lat).buffer(deg_radius)

        details = (
            f"next_month={next_m}, season={season_next}, "
            f"avg_rain_days={avg_rain_days:.2f}, baseline_days={baseline}"
        )

        results.append(
            ForecastResult(
                model=model,
                forecast_date=timezone.localtime(now).date(),
                predicted_at=timezone.localtime(now),
                area_name=city,
                risk_level=risk_level,
                confidence=confidence,
                details=details,
                affected_area=polygon,
            )
        )

        if risk_level in ("medium", "high"):
            to_alert.append((city, risk_level, confidence))

    if not results:
        return "No monthly rainfall forecasts created (no historical data)."

    with transaction.atomic():
        ForecastResult.objects.bulk_create(results, batch_size=200)

    # Send alerts after write
    sent = 0
    for city, risk, conf in to_alert:
        send_alert(
            title=f"🌧️ Rainfall Forecast Warning: {city}",
            message=(
                f"Next month ({next_m}) rainfall in {city} is projected below seasonal norms. "
                f"Risk: {risk.upper()} — Confidence: {conf*100:.1f}%."
            ),
            severity="warning" if risk == "medium" else "critical",
        )
        sent += 1

    return f"Monthly rainfall forecast created for {len(results)} cities; {sent} alerts sent."


@shared_task
def run_dry_season_alerts() -> str:
    """
    Despite the name, this monitors *rainy-season* anomalies (delayed/missing rain)
    city-by-city using `detect_drought_anomaly(city)`.
    - Runs only if Africa/Lusaka's current month is in the rainy season.
    - Creates ForecastResult rows in bulk and then sends alerts for MEDIUM/HIGH.
    """
    now = timezone.now()
    lusaka_now = timezone.localtime(now)
    month = _lusaka_month(now)
    season = get_season(month)

    # Only run during the rainy season; silent no-op otherwise
    if season != "rainy":
        return "Not rainy season — skipping anomaly check."

    model, _ = ForecastModel.objects.get_or_create(
        name="Rainy Season Anomaly Monitor",
        model_type="drought",
        defaults={"description": "Detects lack of rain during rainy season as potential drought indicator."},
    )

    results_to_create: List[ForecastResult] = []
    alerts_to_send: list[tuple[str, str, float]] = []  # (city, risk_level, confidence)

    # Use a city-wide footprint (~8 km) for advisories
    default_buffer_m = 8_000.0

    for city, lon, lat in ZAMBIA_CITIES:
        outcome = detect_drought_anomaly(city)
        if not outcome:
            continue

        risk_level = str(outcome.get("risk_level", "medium"))
        # Fixed confidence here; you can lift from `outcome` if you compute it there
        confidence = float(outcome.get("confidence", 0.8))
        details = str(outcome.get("message", ""))

        # Build polygon buffer around city point
        deg_radius = _degree_buffer_for_meters(lat, meters=default_buffer_m)
        polygon = Point(lon, lat).buffer(deg_radius)

        results_to_create.append(
            ForecastResult(
                model=model,
                forecast_date=lusaka_now.date(),
                predicted_at=lusaka_now,
                area_name=city,
                risk_level=risk_level,
                confidence=confidence,
                details=details,
                affected_area=polygon,
            )
        )

        if risk_level in ("medium", "high"):
            alerts_to_send.append((city, risk_level, confidence))

    if not results_to_create:
        return "No rainy-season anomalies detected."

    # Persist and then alert
    with transaction.atomic():
        ForecastResult.objects.bulk_create(results_to_create, batch_size=200)

    sent = 0
    for city, risk, conf in alerts_to_send:
        send_alert(
            title=f"🌧️ Rainy Season Anomaly: {city}",
            message=f"{city}: {risk.upper()} risk — {int(conf*100)}% confidence. Possible delayed rains/early drought.",
            severity="warning" if risk == "medium" else "critical",
        )
        sent += 1

    return f"{len(results_to_create)} rainy-season anomaly results saved; {sent} alerts sent."

@shared_task
def run_seasonal_outlook() -> str:
    # 1) Load model
    try:
        model_path = "disaster_management/forecasts/ml/seasonal_outlook_model.joblib"
        model = joblib.load(model_path)
        print(f"[✓] Model loaded: {model_path}")
    except Exception as e:
        msg = f"[!] Failed to load seasonal outlook model: {e}"
        print(msg)
        return msg

    # 2) Define rainy window and fetch logs (minimal columns)
    now = timezone.now()
    window_start, window_end = _current_rainy_window(now)
    tz = timezone.get_current_timezone()

    qs = (
        WeatherLog.objects
        .filter(recorded_at__gte=window_start, recorded_at__lte=window_end)
        .only("city_name", "recorded_at", "condition", "rainfall_mm")
        .exclude(city_name__isnull=True)
        .exclude(city_name__exact="")
    )
    count_logs = qs.count()
    print(f"[✓] Fetched {count_logs} weather logs in rainy window {window_start.date()} → {window_end.date()}")

    if count_logs == 0:
        return "No data available for seasonal prediction."

    # 3) Define 'rainy' condition: prefer rainfall_mm>0 if present, else condition text
    rain_q = Q(condition__iregex=r"(rain|storm|showers|thunder)")
    try:
        rain_q = rain_q | Q(rainfall_mm__gt=0)
    except Exception:
        pass

    # 4) Count DISTINCT rainy days per city *per month* (local date bucketing)
    rainy_days = (
        qs.filter(rain_q)
        .annotate(date_local=TruncDate("recorded_at", tzinfo=tz),
                  month=ExtractMonth("recorded_at"))
        .values("city_name", "month")
        .annotate(rain_days=Count("date_local", distinct=True))
    )

    # Build city -> {month: rainy_day_count}
    city_month_counts: Dict[str, Dict[int, int]] = {}
    for row in rainy_days:
        city = row["city_name"]
        m = int(row["month"])
        d = int(row["rain_days"])
        city_month_counts.setdefault(city, {})[m] = d

    if not city_month_counts:
        print("[!] No cities found with valid rainy-day data.")
        return "No data available for seasonal prediction."

    # 5) Create/ensure model entry
    model_entry, _ = ForecastModel.objects.get_or_create(
        name="Seasonal Outlook Predictor",
        model_type="drought",
        defaults={"description": "ML model for seasonal drought outlook"},
    )

    # 6) Prepare predictions
    coord_map = _city_coord_map()
    results: List[ForecastResult] = []
    alerts = 0

    for city, month_map in city_month_counts.items():
        # Keep your model's feature order [Dec, Jan, Feb, Mar]
        features = [[month_map.get(12, 0),
                     month_map.get(1, 0),
                     month_map.get(2, 0),
                     month_map.get(3, 0)]]

        try:
            label = model.predict(features)[0]
        except Exception as e:
            print(f"[!] Prediction failed for {city}: {e}")
            continue

        # Try to derive confidence if model supports predict_proba
        confidence = 0.8
        try:
            proba = model.predict_proba(features)
            if proba is not None and hasattr(model, "classes_"):
                # Confidence = max probability for the predicted class
                import numpy as np
                idx = list(model.classes_).index(label)
                confidence = float(np.clip(proba[0][idx], 0.5, 1.0))
        except Exception:
            pass

        risk = _label_to_risk(str(label))

        # Geometry: ~10 km buffer around city point if we know it
        lon, lat = coord_map.get(city, (None, None))
        polygon = None
        if lon is not None and lat is not None:
            try:
                deg_radius = _degree_buffer_for_meters(lat, meters=10_000.0)
                polygon = Point(lon, lat).buffer(deg_radius)
            except Exception:
                polygon = None

        details = (
            f"window={window_start.date()}→{window_end.date()}, "
            f"features=[Dec:{month_map.get(12, 0)}, Jan:{month_map.get(1, 0)}, "
            f"Feb:{month_map.get(2, 0)}, Mar:{month_map.get(3, 0)}], "
            f"label={label}"
        )

        results.append(
            ForecastResult(
                model=model_entry,
                forecast_date=timezone.localtime(now).date(),
                predicted_at=timezone.localtime(now),
                area_name=city,
                risk_level=risk,
                confidence=confidence,
                details=details,
                affected_area=polygon,
            )
        )

    if not results:
        return "No seasonal outlook results created."

    # 7) Persist results and send notifications for 'failed' with high confidence
    with transaction.atomic():
        ForecastResult.objects.bulk_create(results, batch_size=200)

    for res in results:
        if res.risk_level == "high" and res.confidence >= 0.75:
            # email
            try:
                send_seasonal_alert_email(res.area_name, "failed", res.confidence)
            except Exception as e:
                print(f"[!] Email alert failed for {res.area_name}: {e}")

            # in-app/global notification
            try:
                Notification.objects.create(
                    title=f"{res.area_name} Seasonal Outlook: FAILED",
                    message=(
                        f"{res.area_name} is projected to experience a FAILED rainfall season "
                        f"with {res.confidence*100:.1f}% confidence."
                    ),
                    target_type="global",
                    severity="critical",
                )
            except Exception as e:
                print(f"[!] Notification create failed for {res.area_name}: {e}")
            alerts += 1

    print(f"[✓] Seasonal outlook prediction completed for {len(results)} cities; {alerts} critical alerts.")
    return f"Seasonal outlook task completed for {len(results)} cities; {alerts} critical alerts sent."