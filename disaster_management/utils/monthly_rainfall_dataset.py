# forecasts/utils/monthly_rainfall_dataset.py
from __future__ import annotations

import pandas as pd
from django.utils import timezone
from django.db.models import Q, Count
from django.db.models.functions import TruncDate, ExtractYear, ExtractMonth

from disaster_management.apps.weather.models import WeatherLog


def build_rainfall_training_set() -> pd.DataFrame:
    """
    Build a monthly rainfall training dataset with DISTINCT rainy-day counts.
    Returns a DataFrame with columns:
      city, year, month, rain_days, total_days, rain_ratio
    Notes:
      - Uses Africa/Lusaka local dates for day bucketing.
      - "Rainy" prefers rainfall_mm > 0 if available; falls back to condition text.
      - Works efficiently via DB aggregation (no per-row Python loops).
    """
    tz = timezone.get_current_timezone()

    # Base queryset with only the columns we need
    base_qs = (
        WeatherLog.objects
        .all()
        .only("city_name", "recorded_at", "condition", "rainfall_mm")
        .annotate(
            date_local=TruncDate("recorded_at", tzinfo=tz),
            year=ExtractYear("recorded_at"),
            month=ExtractMonth("recorded_at"),
        )
    )

    # Define "rainy" condition (prefer numeric rainfall if field exists)
    rain_q = Q(condition__iregex=r"(rain|storm|showers|thunder)")
    try:
        # If the field exists, include it
        rain_q = rain_q | Q(rainfall_mm__gt=0)
    except Exception:
        pass

    # 1) Total DISTINCT days logged per city/year/month
    totals = (
        base_qs
        .values("city_name", "year", "month")
        .annotate(total_days=Count("date_local", distinct=True))
        .order_by("city_name", "year", "month")
    )

    # 2) DISTINCT rainy days per city/year/month
    rainy = (
        base_qs.filter(rain_q)
        .values("city_name", "year", "month")
        .annotate(rain_days=Count("date_local", distinct=True))
        .order_by("city_name", "year", "month")
    )

    # Convert to DataFrames and merge
    df_totals = pd.DataFrame(list(totals))
    df_rainy = pd.DataFrame(list(rainy))

    if df_totals.empty:
        # No data; return an empty but well-shaped frame
        return pd.DataFrame(columns=["city", "year", "month", "rain_days", "total_days", "rain_ratio"])

    df = df_totals.merge(
        df_rainy,
        on=["city_name", "year", "month"],
        how="left",
    )

    df["rain_days"] = df["rain_days"].fillna(0).astype(int)
    df["total_days"] = df["total_days"].fillna(0).astype(int)

    # Avoid divide-by-zero; where total_days == 0, set ratio to 0
    df["rain_ratio"] = df.apply(
        lambda r: (r["rain_days"] / r["total_days"]) if r["total_days"] > 0 else 0.0,
        axis=1,
    )

    # Rename city field and sort
    df = df.rename(columns={"city_name": "city"})[
        ["city", "year", "month", "rain_days", "total_days", "rain_ratio"]
    ].sort_values(["city", "year", "month"]).reset_index(drop=True)

    return df
