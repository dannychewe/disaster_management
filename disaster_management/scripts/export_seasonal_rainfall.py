import pandas as pd
from django.utils import timezone
from disaster_management.apps.weather.models import WeatherLog
from collections import defaultdict

def export_monthly_rainfall_csv(filename="seasonal_training_data.csv"):
    logs = WeatherLog.objects.filter(recorded_at__year__gte=2018)
    
    data = defaultdict(lambda: defaultdict(int))  # {(city, year): {month: rain_days}}

    for log in logs:
        month = log.recorded_at.month
        if month in [12, 1, 2, 3]:
            key = (log.city_name, log.recorded_at.year if month != 12 else log.recorded_at.year + 1)
            if log.condition.lower() in ["rain", "storm"]:
                data[key][month] += 1

    rows = []
    for (city, year), months in data.items():
        rows.append({
            "city": city,
            "year": year,
            "rain_dec": months.get(12, 0),
            "rain_jan": months.get(1, 0),
            "rain_feb": months.get(2, 0),
            "rain_mar": months.get(3, 0),
            "season_label": ""  # You’ll fill this manually in Excel
        })

    df = pd.DataFrame(rows)
    df.to_csv(filename, index=False)
    print(f"✅ Exported {len(df)} rows to {filename}")
