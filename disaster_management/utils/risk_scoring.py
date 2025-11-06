from __future__ import annotations

import numpy as np
import pandas as pd

def _normalize(x, lo, hi):
    if hi == lo:
        return 0.0
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))

def score_flood_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Expects columns from extract_flood_features:
      rain_flag, rainfall_recent_24h, rainfall_recent_72h, temp_anomaly,
      flood_history, flood_season_mult
    Returns df with flood_risk (0..1).
    """
    if df.empty:
        return df.assign(flood_risk=pd.Series(dtype=float))

    s24  = df.get("rainfall_recent_24h", 0).fillna(0)
    s72  = df.get("rainfall_recent_72h", 0).fillna(0)
    rain = df.get("rain_flag", 0).fillna(0)
    anom = df.get("temp_anomaly", 0).fillna(0)
    hist = df.get("flood_history", 0).fillna(0)
    mult = df.get("flood_season_mult", 1.0).fillna(1.0)

    # Heuristic components (weights tuned conservatively)
    c_intensity   = s24.apply(lambda v: _normalize(v, 0, 6))            # 0–6 events/24h
    c_persistence = s72.apply(lambda v: _normalize(v, 0, 12))           # 0–12 events/72h
    c_rainflag    = rain.astype(float) * 0.6
    c_temp        = anom.apply(lambda v: _normalize(v, 0, 6)) * 0.3     # warm anomalies boost convection
    c_history     = hist.astype(float) * 0.5                            # prior floods nearby

    raw = (0.35 * c_intensity + 0.25 * c_persistence + 0.20 * c_rainflag +
           0.10 * c_temp + 0.10 * c_history)

    return df.assign(flood_risk=(raw * mult).clip(0, 1))

def score_drought_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Expects columns from extract_drought_features:
      rain, rain_deficit, temperature, humidity, temp_anomaly, drought_season_mult
    Returns df with drought_risk (0..1).
    """
    if df.empty:
        return df.assign(drought_risk=pd.Series(dtype=float))

    deficit = df.get("rain_deficit", 0).fillna(0)            # expected - observed
    temp    = df.get("temperature", 0).fillna(0)
    humid   = df.get("humidity", 50).fillna(50)
    anom    = df.get("temp_anomaly", 0).fillna(0)
    mult    = df.get("drought_season_mult", 1.0).fillna(1.0)

    c_deficit = deficit.apply(lambda v: _normalize(v, 0, 5))            # 0–5 missing rainy days
    c_temp    = temp.apply(lambda v: _normalize(v, 20, 38))
    c_anom    = anom.apply(lambda v: _normalize(v, 0, 8))
    c_dryair  = humid.apply(lambda v: _normalize(60 - v, 0, 40))        # drier → higher risk

    raw = (0.45 * c_deficit + 0.25 * c_temp + 0.20 * c_dryair + 0.10 * c_anom)

    return df.assign(drought_risk=(raw * mult).clip(0, 1))
