from django.db import models
from django.contrib.gis.db import models as gis_models
from django.conf import settings
from django.utils import timezone

from disaster_management.apps.incidents.models import Incident

class Resource(models.Model):
    CATEGORY_CHOICES = [
        ('medical', 'Medical'),
        ('food', 'Food'),
        ('shelter', 'Shelter Supplies'),
        ('rescue', 'Rescue Kits'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    total_stock = models.PositiveIntegerField(default=0, help_text="Initial or baseline stock count.")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.category})"

    @property
    def current_stock(self):
        """Live available stock = sum of all inbound - outbound inventory transactions."""
        total = self.inventory_entries.aggregate(total=models.Sum("quantity"))["total"] or 0
        return total




class ResourceUnit(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('deployed', 'Deployed'),
        ('maintenance', 'Maintenance'),
    ]

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='units')
    serial_number = models.CharField(max_length=100, unique=True, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    is_available = models.BooleanField(default=True)

    assigned_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_units'
    )
    assigned_incident = models.ForeignKey(
        'incidents.Incident',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_units'
    )
    current_location = gis_models.PointField(geography=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Keep is_available automatically synced with status."""
        self.is_available = self.status == 'available'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Unit of {self.resource.name} - {self.serial_number or 'N/A'}"

    
    
class ResourceRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("denied", "Denied"),
    ]

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resource_requests"
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="requests"
    )
    quantity = models.PositiveIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    admin_note = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_requests"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.resource.name} ({self.quantity}) by {self.requester.email}"





class ResourceDeployment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('en_route', 'En Route'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='deployments')
    quantity = models.PositiveIntegerField()
    destination = gis_models.PointField(geography=True)
    deployed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='deployments'
    )
    deployment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    deployed_at = models.DateTimeField(default=timezone.now)

    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name='deployments',
        null=True,
        blank=True,
        help_text="Incident this resource was deployed for."
    )

    def __str__(self):
        return f"{self.resource.name} - {self.quantity} units deployed"


class Inventory(models.Model):
    TRANSACTION_TYPES = [
        ('in', 'Inbound / Stock Add'),
        ('out', 'Outbound / Deployment'),
        ('return', 'Returned Stock'),
        ('adjustment', 'Manual Adjustment'),
    ]

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="inventory_entries")
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField()
    transaction_type = models.CharField(max_length=15, choices=TRANSACTION_TYPES, default='in')
    batch_id = models.CharField(max_length=50, blank=True, null=True)
    source_warehouse = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        direction = "➕" if self.transaction_type == "in" else "➖"
        return f"{direction} {self.quantity} {self.resource.name} ({self.transaction_type})"

    @property
    def signed_quantity(self):
        """Return quantity as positive or negative based on transaction type."""
        if self.transaction_type in ["out"]:
            return -self.quantity
        return self.quantity