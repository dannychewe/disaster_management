

from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
from disaster_management.apps.resources.models import Inventory
from django.db.models import Sum

@receiver(post_save, sender=Inventory)
def check_low_stock(sender, instance, **kwargs):
    resource = instance.resource
    if resource.current_stock < 10:  # Threshold can be dynamic
        send_mail(
            subject=f"[Low Stock Alert] {resource.name}",
            message=f"Only {resource.current_stock} units left for {resource.name}. Please restock.",
            from_email="alerts@disaster-response.com",
            recipient_list=["supply@relief.org", "admin@response.net"],
        )
        
@receiver(post_save, sender=Inventory)
def update_resource_stock(sender, instance, **kwargs):
    total = (
        Inventory.objects.filter(resource=instance.resource)
        .aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    instance.resource.total_stock = total
    instance.resource.save(update_fields=["total_stock", "updated_at"])