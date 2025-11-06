import math
import pandas as pd
from dataclasses import dataclass
from datetime import timedelta
from django.utils import timezone
from django.contrib.gis.measure import D
from typing import Dict, Tuple

from disaster_management.apps.weather.models import WeatherLog


    
RAINY_SEASON_MONTHS   = [11, 12, 1, 2, 3, 4]   # Nov–Apr (peak Dec–Mar)
COOL_DRY_MONTHS       = [5, 6, 7, 8]           # May–Aug
HOT_DRY_MONTHS        = [9, 10]                # Sep–Oct

MONTHLY_TEMP_BASELINE: Dict[int, int] = {
    1: 28, 2: 28, 3: 27, 4: 26,
    5: 24, 6: 22, 7: 22, 8: 24,
    9: 29, 10: 31, 11: 30, 12: 29,
}


ZAMBIA_COORDINATES = [
    {"city": "Lusaka", "lat": -15.3875, "lon": 28.3228},
    {"city": "Ndola", "lat": -12.9587, "lon": 28.6366},
    {"city": "Kitwe", "lat": -12.8156, "lon": 28.2132},
    {"city": "Livingstone", "lat": -17.8572, "lon": 25.8567},
    {"city": "Chipata", "lat": -13.6367, "lon": 32.6455},
    {"city": "Kasama", "lat": -10.2129, "lon": 31.1800},
    {"city": "Mansa", "lat": -11.1998, "lon": 28.8943},
    {"city": "Solwezi", "lat": -12.1833, "lon": 26.4000},
    {"city": "Choma", "lat": -16.8122, "lon": 26.9833},
    {"city": "Mongu", "lat": -15.2796, "lon": 23.1274},
    {"city": "Kabwe", "lat": -14.4469, "lon": 28.4464},
    {"city": "Mazabuka", "lat": -15.8580, "lon": 27.7485},
    {"city": "Siavonga", "lat": -16.5380, "lon": 28.7087},
    {"city": "Mpika", "lat": -11.8366, "lon": 31.4521},
]

def get_season(month: int) -> str:
    if month in RAINY_SEASON_MONTHS:
        return "rainy"
    if month in COOL_DRY_MONTHS:
        return "cool_dry"
    return "hot_dry"  # 9–10

def _lusaka_month(dt) -> int:
    """Return the calendar month in Africa/Lusaka for a given aware datetime."""
    return timezone.localtime(dt).month

def is_rain_season(month: int) -> bool:
    return month in RAINY_SEASON_MONTHS

def is_heat_season(month: int) -> bool:
    return month in HOT_DRY_MONTHS
@dataclass(frozen=True)
class SeasonalWeights:
    # Multipliers for converting raw features into season-aware risk signals
    flood_mult: float   # how much to up/down-weight flood risk in this season
    drought_mult: float # how much to up/down-weight drought risk in this season
    expected_rain_days_last7: int  # used to gauge rain deficit

SEASON_CONFIG = {
    "rainy": SeasonalWeights(flood_mult=1.25, drought_mult=0.75, expected_rain_days_last7=3),
    "cool_dry": SeasonalWeights(flood_mult=0.85, drought_mult=1.0, expected_rain_days_last7=1),
    "hot_dry": SeasonalWeights(flood_mult=0.75, drought_mult=1.25, expected_rain_days_last7=0),
}


def _rain_indicator(log: "WeatherLog") -> int:
    """
    Binary rain flag. Prefer numeric `rainfall_mm` if available:
    return 1 if (getattr(log, "rainfall_mm", 0) or 0) > 0 else 0
    """
    cond = (getattr(log, "condition", "") or "").strip().lower()
    return 1 if cond in {"rain", "storm", "thunderstorm", "showers"} else 0


def _temp_anomaly(temp: float | None, month: int) -> float:
    baseline = MONTHLY_TEMP_BASELINE.get(month)
    if baseline is None or temp is None:
        return 0.0
    return float(temp - baseline)

def _recent_rain_counts(now=None, *, window_hours: int = 24) -> Dict[Tuple[float, float], int]:
    """
    Precompute { (lat, lon) rounded key : rain_count } for the last `window_hours`.
    Keys are rounded to 2 decimal places to form ~local buckets.
    """
    from disaster_management.apps.weather.models import WeatherLog as _WL  # local import
    if now is None:
        now = timezone.now()
    since = now - timedelta(hours=window_hours)
    qs = (
        _WL.objects
        .filter(recorded_at__gte=since)
        .only("location", "condition")
    )

    buckets: Dict[Tuple[float, float], int] = {}
    for log in qs:
        if not getattr(log, "location", None):
            continue
        lat = round(log.location.y, 2)
        lon = round(log.location.x, 2)
        key = (lat, lon)
        buckets[key] = buckets.get(key, 0) + _rain_indicator(log)
    return buckets


ZAMBIA_CITIES = [
    ("Lusaka", 28.3228, -15.3875),
    ("Ndola", 28.6366, -12.9587),
    ("Kitwe", 28.2132, -12.8156),
]