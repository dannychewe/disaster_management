# forecasts/predictors/seasonal_outlook.py
import joblib
import pandas as pd

MODEL_PATH = "disaster_management/forecasts/ml/seasonal_outlook_model.joblib"

def predict_seasonal_outlook(df):
    model = joblib.load(MODEL_PATH)

    features = df[["rain_jan", "rain_feb", "rain_mar", "rain_dec"]]
    df["prediction"] = model.predict(features)

    return df[["city", "year", "prediction"]]
