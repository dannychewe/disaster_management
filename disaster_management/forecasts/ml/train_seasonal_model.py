# forecasts/train_seasonal_model.py
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib

df = pd.read_csv("seasonal_training_data.csv")

X = df[["rain_jan", "rain_feb", "rain_mar", "rain_dec"]]  # features
y = df["season_label"]  # labels

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

clf = RandomForestClassifier()
clf.fit(X_train, y_train)

print(classification_report(y_test, clf.predict(X_test)))

joblib.dump(clf, "disaster_management/forecasts/ml/seasonal_outlook_model.joblib")
