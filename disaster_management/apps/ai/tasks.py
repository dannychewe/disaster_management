from celery import shared_task
from django.contrib.gis.measure import D
from disaster_management.apps.ai.models import IncidentAIAnalysis
from disaster_management.apps.incidents.models import Incident
from disaster_management.apps.ai.scoring import compute_risk_score
from disaster_management.apps.users.models import User
from disaster_management.utils.notifications import notify_users


@shared_task
def ai_score_incident(incident_id):
    """Compute AI score and update incident record."""
    incident = Incident.objects.get(id=incident_id)
    result = compute_risk_score(incident)

    IncidentAIAnalysis.objects.update_or_create(incident=incident, defaults=result)

    # Update Incident directly
    incident.risk_score = result["risk_score"]
    incident.risk_label = result["label"]
    incident.risk_confidence = result["confidence"]
    incident.risk_drivers = result["drivers"]
    incident.ai_version = result["version"]
    incident.save(update_fields=[
        "risk_score", "risk_label", "risk_confidence",
        "risk_drivers", "ai_version"
    ])

    # Notify on high-risk incidents
    if result["risk_score"] >= 75:
        admins = User.objects.filter(role__in=["Admin", "Responder"], is_active=True)
        message = (
            f"A new {incident.incident_type.get_name_display()} incident was scored HIGH RISK "
            f"({result['risk_score']:.1f}/100).\n\n"
            f"Location: ({incident.location.y:.4f}, {incident.location.x:.4f})"
        )
        notify_users(
            title="⚠️ High-Risk Incident Detected",
            message=message,
            users=list(admins),
            severity="critical",
        )

    # Chain to cluster detection
    detect_spatial_clusters.delay(incident.id)
    return result


@shared_task
def detect_spatial_clusters(incident_id, radius_km=3):
    """Detect nearby incidents and raise a cluster alert if found."""
    try:
        incident = Incident.objects.get(id=incident_id)
    except Incident.DoesNotExist:
        return "Incident not found."

    nearby = (
        Incident.objects
        .filter(location__distance_lte=(incident.location, D(km=radius_km)))
        .exclude(id=incident.id)
    )
    count = nearby.count()
    if count < 2:
        return "No cluster detected."

    adjustment = min(20, 5 * count)
    incident.risk_score = (incident.risk_score or 0) + adjustment
    incident.risk_label = "High"
    incident.save(update_fields=["risk_score", "risk_label"])

    # Notify admins/responders
    admins = User.objects.filter(role__in=["Admin", "Responder"], is_active=True)
    message = (
        f"{count + 1} incidents have been reported within {radius_km} km of "
        f"({incident.location.y:.3f}, {incident.location.x:.3f}).\n"
        "The area is now flagged as a HIGH-RISK cluster."
    )
    notify_users(
        title=f"Incident Cluster Detected — {incident.incident_type.get_name_display()}",
        message=message,
        users=list(admins),
        severity="critical",
    )
    return f"Cluster detected near incident #{incident.id}"



@shared_task
def build_hotspots(window_days: int = 7, radius_km: float = 3.0):
    """
    1) Pull incidents within window
    2) Run DBSCAN on (lat, lon) in radians with haversine
    3) Persist IncidentHotspot with intensity
    """
    from django.utils import timezone
    from sklearn.cluster import DBSCAN
    import numpy as np
    from math import radians
    from disaster_management.apps.incidents.models import Incident, IncidentHotspot
    now = timezone.now()
    since = now - timezone.timedelta(days=window_days)

    qs = (Incident.objects
          .filter(reported_at__gte=since)
          .only("id","location","incident_type","risk_score"))

    pts = []
    meta = []
    for inc in qs:
        if not inc.location:
            continue
        lat, lon = float(inc.location.y), float(inc.location.x)
        pts.append([radians(lat), radians(lon)])
        meta.append((inc.incident_type.name, float(inc.risk_score or 0.0)))

    if not pts:
        return "No incidents in window"

    X = np.array(pts)
    eps_rad = radius_km / 6371.0088  # km → radians
    db = DBSCAN(eps=eps_rad, min_samples=3, metric="haversine").fit(X)
    labels = db.labels_
    if (labels < 0).all():
        return "No clusters found"

    # wipe old hotspots for this window
    IncidentHotspot.objects.filter(window=f"{window_days}d").delete()

    # aggregate clusters
    for lab in set(labels):
        if lab < 0:
            continue
        idx = np.where(labels == lab)[0]
        lat_deg = [np.degrees(X[i,0]) for i in idx]
        lon_deg = [np.degrees(X[i,1]) for i in idx]
        cen_lat = float(np.mean(lat_deg))
        cen_lon = float(np.mean(lon_deg))
        intensity = float(np.mean([meta[i][1] for i in idx])) if idx.size else 0.0
        # simple circle area; replace with concave hull later if desired
        from django.contrib.gis.geos import Point
        from math import cos
        deg_rad = radius_km / 111.32  # rough
        area = Point(cen_lon, cen_lat).buffer(deg_rad)
        types = [meta[i][0] for i in idx]
        dom = max(set(types), key=types.count)

        IncidentHotspot.objects.create(
            window=f"{window_days}d",
            centroid=Point(cen_lon, cen_lat),
            area_geom=area,
            intensity=intensity,
            dominant_type=dom,
        )

    return "Hotspots updated"



@shared_task
def forecast_near_term_flood(incident_id):
    """
    MVP: combine lagged rain features + river proximity into a heuristic probability.
    Later: fit XGBoost per admin cell.
    """
    from disaster_management.apps.incidents.models import Incident
    inc = Incident.objects.get(id=incident_id)
    w = getattr(inc, "weather_features", None)
    s = getattr(inc, "spatial_context", None)
    if not w or not s:
        return "Missing features"

    # crude heuristic model
    p = (0.5 * float(w.rain_30d_pct) +
         0.3 * float(w.forecast_7d_risk) +
         0.2 * float(s.proximity_water))
    p = float(max(0, min(1, p)))
    # You can store on incident or a new table; keep it simple for now:
    inc.risk_drivers = {**(inc.risk_drivers or {}), "flood_prob_0_7d": round(p,3)}
    inc.save(update_fields=["risk_drivers"])
    return p
