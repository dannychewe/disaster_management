# scoring.py
from .nlp import text_severity_prob
from .vision import image_evidence_score
from django.contrib.gis.geos import Point

def _normalize01(x):  # guard
    try:
        return float(max(0.0, min(1.0, x)))
    except:
        return 0.0

def _get_weather_features(incident):
    wf = getattr(incident, "weather_features", None)
    return {
        "rain30": _normalize01(getattr(wf, "rain_30d_pct", 0.0)),
        "fcast7": _normalize01(getattr(wf, "forecast_7d_risk", 0.0)),
        "wind7":  _normalize01(getattr(wf, "wind_7d", 0.0)),
    }

def _get_spatial_features(incident):
    sc = getattr(incident, "spatial_context", None)
    return {
        "prox_water": _normalize01(getattr(sc, "proximity_water", 0.0)),   # assume 0..1
        "infra":      _normalize01(getattr(sc, "infra_exposure", 0.0)),    # 0..1 (pop/roads exposure)
    }

def _image_score(incident, hazard):
    media = list(incident.media.all()[:3])  # cap read
    if not media:
        return 0.2
    # take max evidence across first few images
    best = 0.0
    for m in media:
        try:
            with m.media_file.open("rb") as f:
                s = image_evidence_score(f, hazard)
                best = max(best, s)
        except:
            pass
    return float(best)

def compute_risk_score(incident):
    hazard = incident.incident_type.name  # 'flood','drought',...
    text_prob = text_severity_prob(incident.description or "", hazard)
    w = _get_weather_features(incident)
    s = _get_spatial_features(incident)
    img = _image_score(incident, hazard)

    # Weight recipe (Phase-0)
    # report_conf*0.25 + rain30*0.25 + forecast7*0.20 + proximity*0.10 + infra*0.10 + image*0.10
    score01 = (
        0.25 * text_prob +
        0.25 * w["rain30"] +
        0.20 * w["fcast7"] +
        0.10 * s["prox_water"] +
        0.10 * s["infra"] +
        0.10 * img
    )
    score = float(round(score01 * 100, 1))
    label = "High" if score >= 75 else "Medium" if score >= 40 else "Low"

    drivers = {
        "report_conf": round(text_prob, 3),
        "rain_30d_pct": round(w["rain30"], 3),
        "forecast_7d_risk": round(w["fcast7"], 3),
        "proximity_water": round(s["prox_water"], 3),
        "infra_exposure": round(s["infra"], 3),
        "image_score": round(img, 3),
    }
    explanation = (
        f"{label} risk: text={drivers['report_conf']}, rain30={drivers['rain_30d_pct']}, "
        f"fcst7={drivers['forecast_7d_risk']}, water={drivers['proximity_water']}, "
        f"infra={drivers['infra_exposure']}, img={drivers['image_score']}."
    )

    return {
        "risk_score": score,
        "confidence": 0.6 + 0.4 * score01,  # simple calibration proxy
        "label": label,
        "drivers": drivers,
        "version": "v0.1",
        "explanation": explanation,
    }
