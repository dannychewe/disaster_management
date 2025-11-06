from disaster_management.utils.feature_extraction import is_rain_season
from datetime import datetime


def predict(df):
    """Return drought risk based on recent weather trends and seasonal context."""
    predictions = []
    current_month = datetime.now().month

    for _, row in df.iterrows():
        if is_rain_season(current_month):
            # More sensitive to dry spells
            if row["rain"] == 0 and row["temperature"] > 30 and row["humidity"] < 40:
                risk = "high"
                confidence = 0.85
            elif row["rain"] < 2 and row["temperature"] > 28:
                risk = "medium"
                confidence = 0.6
            else:
                risk = "low"
                confidence = 0.3
        else:
            # During dry season, lower the baseline risk
            risk = "low"
            confidence = 0.2

        predictions.append((risk, confidence))

    return predictions