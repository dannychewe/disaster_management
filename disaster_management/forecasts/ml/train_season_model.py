# forecasts/ml/train_season_model.py
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import joblib
import os

# Load the dataset
CSV_PATH = "disaster_management/forecasts/ml/seasonal_training_data.csv"
MODEL_PATH = "disaster_management/forecasts/ml/seasonal_outlook_model.joblib"

def train_seasonal_model():
    if not os.path.exists(CSV_PATH):
        return f"[!] Missing file: {CSV_PATH}"

    df = pd.read_csv(CSV_PATH)

    # Basic checks
    required_cols = ["city", "year", "rain_dec", "rain_jan", "rain_feb", "rain_mar", "season_label"]
    if not all(col in df.columns for col in required_cols):
        return f"[!] Missing required columns in dataset."

    # Prepare training data
    X = df[["rain_dec", "rain_jan", "rain_feb", "rain_mar"]]
    y = df["season_label"]

    # Train model
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)

    # Save model
    joblib.dump(model, MODEL_PATH)
    return f"[✓] Model trained and saved to {MODEL_PATH}"
