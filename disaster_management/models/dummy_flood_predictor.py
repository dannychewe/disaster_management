import numpy as np

def predict(df):
    """Return dummy risk levels based on rainfall and flood history."""
    risk_levels = []
    for _, row in df.iterrows():
        if row["rainfall"] > 0.8 and row["flood_history"] > 0:
            risk_levels.append(("high", 0.9))
        elif row["rainfall"] > 0.5:
            risk_levels.append(("medium", 0.6))
        else:
            risk_levels.append(("low", 0.3))
    return risk_levels
