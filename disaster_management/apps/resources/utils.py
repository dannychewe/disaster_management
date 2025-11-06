from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum

def get_average_daily_deployment(resource, days=7):
    today = timezone.now()
    week_ago = today - timedelta(days=days)
    total = resource.deployments.filter(deployed_at__gte=week_ago).aggregate(Sum("quantity"))["quantity__sum"] or 0
    return total / days

def recommend_restock(resource, projected_days=3):
    avg_daily = get_average_daily_deployment(resource)
    expected_usage = avg_daily * projected_days

    if resource.current_stock < expected_usage:
        return f"Restock {resource.name}: Expected usage in {projected_days} days = {expected_usage:.1f}, current stock = {resource.current_stock}."
    return None

