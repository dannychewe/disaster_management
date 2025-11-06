# forecasts/utils/seasonal_rainfall.py
from __future__ import annotations

from datetime import timedelta
from typing import Optional

import pandas as pd
from django.utils import timezone
from django.db.models import Q, Count
from django.db.models.functions import TruncDate, ExtractYear

from disaster_management.apps.weather.models import WeatherLog


def get_monthly_rainfall_history(
    city_name: str,
    month: int,
    years_back: int = 5,
) -> Optional[float]:
    """
    Return the average number of *rainy days* in the given month for the past `years_back` years.
    - Uses Africa/Lusaka local dates for day bucketing.
    - Counts distinct dates with rain (not raw log rows).
    - Prefers numeric `rainfall_mm` if present; falls back to condition text.
    """
    now = timezone.now()
    local_year = timezone.localtime(now).year
    start_year = local_year - years_back
    tz = timezone.get_current_timezone()

    # Base queryset: target city and month over the past N years
    base_qs = (
        WeatherLog.objects
        .filter(
            city_name__iexact=city_name,
            recorded_at__month=month,
            recorded_at__year__gte=start_year,
        )
        .only("recorded_at", "condition", "rainfall_mm")
    )

    # Define “rainy”:
    # - Prefer rainfall_mm > 0 if the field exists
    # - OR condition text indicates rain/storm/showers/thunder
    rain_q = Q(condition__iregex=r"(rain|storm|showers|thunder)")
    # Not all deployments have rainfall_mm—guard with try/except
    try:
        rain_q = rain_q | Q(rainfall_mm__gt=0)
    except Exception:
        pass

    rainy_qs = base_qs.filter(rain_q)

    # Bucket by *local* date and extract year; count DISTINCT rainy dates per year
    per_year = (
        rainy_qs
        .annotate(
            date_local=TruncDate("recorded_at", tzinfo=tz),
            year=ExtractYear("recorded_at"),
        )
        .values("year")
        .annotate(rain_days=Count("date_local", distinct=True))
        .order_by("year")
    )

    rows = list(per_year)
    if not rows:
        return None

    df = pd.DataFrame(rows)  # columns: ["year", "rain_days"]
    avg_rain_days = float(df["rain_days"].mean())
    return round(avg_rain_days, 2)
