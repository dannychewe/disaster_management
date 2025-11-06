import graphene
from django.contrib.gis.geos import Point
from graphql import GraphQLError
from django.utils import timezone
from django.db import transaction

from disaster_management.apps.resources.models import (
    Inventory,
    Resource,
    ResourceDeployment,
    ResourceUnit,
    ResourceRequest,
)
from disaster_management.apps.incidents.models import Incident
from disaster_management.apps.users.models import User
from disaster_management.graphql.types.resources import (
    ResourceDeploymentType,
    ResourceType,
)
from disaster_management.utils.notifications import notify_users


# ============================================================
# 1️⃣ RESOURCE CRUD
# ============================================================

class CreateResource(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    resource = graphene.Field(ResourceType)

    class Arguments:
        name = graphene.String(required=True)
        category = graphene.String(required=True)
        total_stock = graphene.Int(required=True)

    def mutate(self, info, name, category, total_stock):
        user = info.context.user
        if not user.is_authenticated or getattr(user, "role", "") != "Admin":
            raise GraphQLError("Only Admins can create resources.")

        resource = Resource.objects.create(
            name=name,
            category=category,
            total_stock=total_stock,
        )

        # ✅ Notify all responders + admins
        admins = User.objects.filter(role="Admin")
        responders = User.objects.filter(role="Responder")

        notify_users(
            title="New Resource Created",
            message=f"A new resource '{resource.name}' ({resource.category}) has been added by {user.email}.",
            users=list(admins) + list(responders),
            severity="info",
        )

        return CreateResource(success=True, message="Resource created.", resource=resource)


class UpdateResource(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    resource = graphene.Field(ResourceType)

    class Arguments:
        resource_id = graphene.ID(required=True)
        name = graphene.String(required=False)
        category = graphene.String(required=False)
        total_stock = graphene.Int(required=False)

    def mutate(self, info, resource_id, name=None, category=None, total_stock=None):
        user = info.context.user
        if not user.is_authenticated or getattr(user, "role", "") != "Admin":
            raise GraphQLError("Only Admins can update resources.")

        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist:
            raise GraphQLError("Resource not found.")

        if name:
            resource.name = name
        if category:
            resource.category = category
        if total_stock is not None:
            resource.total_stock = total_stock
        resource.save()

        # ✅ Notify responders and admins
        admins = User.objects.filter(role="Admin")
        responders = User.objects.filter(role="Responder")

        notify_users(
            title="Resource Updated",
            message=f"Resource '{resource.name}' has been updated by {user.email}. Current stock: {resource.total_stock}.",
            users=list(admins) + list(responders),
            severity="info",
        )

        return UpdateResource(success=True, message="Resource updated.", resource=resource)

class DeleteResource(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        resource_id = graphene.ID(required=True)

    def mutate(self, info, resource_id):
        user = info.context.user
        if not user.is_authenticated or getattr(user, "role", "") != "Admin":
            raise GraphQLError("Only Admins can delete resources.")

        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist:
            raise GraphQLError("Resource not found.")

        resource_name = resource.name
        resource.delete()

        # ✅ Notify admins & responders
        admins = User.objects.filter(role="Admin")
        responders = User.objects.filter(role="Responder")

        notify_users(
            title="Resource Deleted",
            message=f"The resource '{resource_name}' has been deleted by {user.email}.",
            users=list(admins) + list(responders),
            severity="warning",
        )

        return DeleteResource(success=True, message="Resource deleted successfully.")


# ============================================================
# 2️⃣ INVENTORY
# ============================================================

class AddInventory(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    resource = graphene.Field(ResourceType)

    class Arguments:
        resource_id = graphene.ID(required=True)
        quantity = graphene.Int(required=True)
        note = graphene.String(required=False)
        batch_id = graphene.String(required=False)
        source_warehouse = graphene.String(required=False)

    def mutate(self, info, resource_id, quantity, note=None, batch_id=None, source_warehouse=None):
        user = info.context.user
        if not user.is_authenticated or getattr(user, "role", "") != "Admin":
            raise GraphQLError("Only Admins can add inventory.")

        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist:
            raise GraphQLError("Resource not found.")

        Inventory.objects.create(
            resource=resource,
            quantity=quantity,
            added_by=user,
            note=note,
            batch_id=batch_id,
            source_warehouse=source_warehouse,
        )

        # ✅ Notify responders about restock
        responders = User.objects.filter(role="Responder")
        notify_users(
            title="Inventory Updated",
            message=f"{quantity} units of '{resource.name}' added to stock by {user.email}.",
            users=list(responders),
            severity="info",
        )

        return AddInventory(success=True, message="Inventory added.", resource=resource)

# ============================================================
# 3️⃣ DEPLOYMENT
# ============================================================

class DeployResource(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    deployment = graphene.Field(ResourceDeploymentType)

    class Arguments:
        resource_id = graphene.ID(required=True)
        quantity = graphene.Int(required=True)
        latitude = graphene.Float(required=True)
        longitude = graphene.Float(required=True)
        incident_id = graphene.ID(required=False)

    @transaction.atomic
    def mutate(self, info, resource_id, quantity, latitude, longitude, incident_id=None):
        user = info.context.user
        if not user.is_authenticated or getattr(user, "role", "") not in ["Admin", "Responder"]:
            raise GraphQLError("Only Admins or Responders can deploy resources.")

        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist:
            raise GraphQLError("Resource not found.")

        if resource.current_stock < quantity:
            raise GraphQLError(f"Insufficient stock. Available: {resource.current_stock}")

        Inventory.objects.create(
            resource=resource,
            quantity=quantity,
            added_by=user,
            note="Auto-deducted by deployment (outgoing)",
            source_warehouse="Deployment",
        )

        resource.total_stock = max(resource.total_stock - quantity, 0)
        resource.save(update_fields=["total_stock"])

        destination = Point(longitude, latitude, srid=4326)
        deployment = ResourceDeployment.objects.create(
            resource=resource,
            quantity=quantity,
            destination=destination,
            deployed_by=user,
            incident_id=incident_id,
        )

        # ✅ Notify admins + responders
        admins = User.objects.filter(role="Admin")
        responders = User.objects.filter(role="Responder")
        msg = f"{quantity} units of '{resource.name}' deployed by {user.email}."

        if incident_id:
            msg += f" Linked to incident #{incident_id}."

        notify_users(
            title="Resource Deployed",
            message=msg,
            users=list(admins) + list(responders),
            severity="info",
        )

        return DeployResource(success=True, message="Resource deployed.", deployment=deployment)

class UpdateDeploymentStatus(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    deployment = graphene.Field(ResourceDeploymentType)

    class Arguments:
        deployment_id = graphene.ID(required=True)
        status = graphene.String(required=True)

    def mutate(self, info, deployment_id, status):
        user = info.context.user
        if not user.is_authenticated or getattr(user, "role", "") not in ["Admin", "Responder"]:
            raise GraphQLError("Permission denied.")

        try:
            deployment = ResourceDeployment.objects.get(id=deployment_id)
        except ResourceDeployment.DoesNotExist:
            raise GraphQLError("Deployment not found.")

        if status not in dict(ResourceDeployment.STATUS_CHOICES):
            raise GraphQLError("Invalid status value.")

        deployment.deployment_status = status
        deployment.save()

        # ✅ Notify admins and responders
        admins = User.objects.filter(role="Admin")
        responders = User.objects.filter(role="Responder")

        notify_users(
            title="Deployment Status Updated",
            message=f"Deployment #{deployment.id} marked as '{status}' by {user.email}.",
            users=list(admins) + list(responders),
            severity="info",
        )

        return UpdateDeploymentStatus(
            success=True, message=f"Deployment marked as {status}.", deployment=deployment
        )


# ============================================================
# 4️⃣ RESOURCE UNITS MANAGEMENT
# ============================================================

class ChangeUnitStatus(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        unit_id = graphene.ID(required=True)
        status = graphene.String(required=True)

    def mutate(self, info, unit_id, status):
        user = info.context.user
        if not user.is_authenticated or getattr(user, "role", "") not in ["Admin", "Responder"]:
            raise GraphQLError("Permission denied.")

        try:
            unit = ResourceUnit.objects.get(id=unit_id)
        except ResourceUnit.DoesNotExist:
            raise GraphQLError("Unit not found.")

        if status not in dict(ResourceUnit.STATUS_CHOICES):
            raise GraphQLError("Invalid status value.")

        unit.status = status
        unit.is_available = status == "available"
        unit.save()

        return ChangeUnitStatus(success=True, message=f"Unit status changed to {status}.")


class BatchAssignUnits(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        unit_ids = graphene.List(graphene.ID, required=True)
        incident_id = graphene.ID(required=False)
        responder_id = graphene.ID(required=False)

    def mutate(self, info, unit_ids, incident_id=None, responder_id=None):
        user = info.context.user
        if not user.is_authenticated or getattr(user, "role", "") != "Admin":
            raise GraphQLError("Only Admins can assign resources.")

        responder = None
        incident = None
        if responder_id:
            responder = User.objects.filter(id=responder_id).first()
        if incident_id:
            incident = Incident.objects.filter(id=incident_id).first()

        if not responder and not incident:
            raise GraphQLError("Provide either an incident_id or responder_id.")

        units = ResourceUnit.objects.filter(id__in=unit_ids)
        for u in units:
            u.assigned_to_user = responder
            u.assigned_incident = incident
            u.status = "deployed"
            u.is_available = False
            u.save()

        target = f"incident {incident_id}" if incident_id else f"responder {responder_id}"
        return BatchAssignUnits(success=True, message=f"Assigned {len(units)} units to {target}.")


# ============================================================
# 5️⃣ RESOURCE REQUESTS (RESPONDER <-> ADMIN)
# ============================================================

class CreateResourceRequest(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        resource_id = graphene.ID(required=True)
        quantity = graphene.Int(required=True)
        reason = graphene.String(required=True)

    def mutate(self, info, resource_id, quantity, reason):
        user = info.context.user
        if not user.is_authenticated or getattr(user, "role", "") != "Responder":
            raise GraphQLError("Only Responders can make requests.")

        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist:
            raise GraphQLError("Resource not found.")

        req = ResourceRequest.objects.create(
            requester=user, resource=resource, quantity=quantity, reason=reason
        )

        # ✅ Notify admins that a request was submitted
        admins = User.objects.filter(role="Admin")
        notify_users(
            title="New Resource Request",
            message=f"Responder {user.email} requested {quantity} units of '{resource.name}'.",
            users=list(admins),
            severity="info",
        )

        return CreateResourceRequest(success=True, message="Resource request submitted.")



class ReviewResourceRequest(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        request_id = graphene.ID(required=True)
        status = graphene.String(required=True)
        admin_note = graphene.String(required=False)

    def mutate(self, info, request_id, status, admin_note=None):
        user = info.context.user
        if not user.is_authenticated or getattr(user, "role", "") != "Admin":
            raise GraphQLError("Only Admins can review requests.")

        try:
            req = ResourceRequest.objects.get(id=request_id)
        except ResourceRequest.DoesNotExist:
            raise GraphQLError("Request not found.")

        if status not in ["approved", "denied"]:
            raise GraphQLError("Invalid status.")

        req.status = status
        req.admin_note = admin_note
        req.reviewed_by = user
        req.reviewed_at = timezone.now()
        req.save()

        return ReviewResourceRequest(success=True, message=f"Request {status}.")





class ApproveResourceRequest(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    request = graphene.Field("disaster_management.graphql.types.ResourceRequestType")

    class Arguments:
        request_id = graphene.ID(required=True)

    def mutate(self, info, request_id):
        user = info.context.user
        if not user.is_authenticated or user.role != "Admin":
            raise GraphQLError("Only admins can approve requests.")

        try:
            req = ResourceRequest.objects.get(id=request_id)
        except ResourceRequest.DoesNotExist:
            raise GraphQLError("Request not found.")

        if req.status.lower() != "pending":
            raise GraphQLError("This request has already been reviewed.")

        if req.resource.current_stock < req.quantity:
            raise GraphQLError("Not enough stock to approve this request.")

        Inventory.objects.create(
            resource=req.resource,
            quantity=req.quantity,
            transaction_type="out",
            added_by=user,
            note=f"Auto-deducted for approved request #{req.id}",
        )

        req.status = "approved"
        req.reviewed_by = user
        req.reviewed_at = timezone.now()
        req.admin_note = f"Approved by {user.email}"
        req.save()

        # ✅ Notify requester (responder)
        notify_users(
            title=f"Resource Request #{req.id} Approved",
            message=f"Your request for {req.quantity} units of '{req.resource.name}' has been approved.",
            users=[req.requester],
            severity="info",
        )

        return ApproveResourceRequest(
            success=True,
            message=f"Request #{req.id} approved and stock deducted.",
            request=req,
        )



class DenyResourceRequest(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    request = graphene.Field("disaster_management.graphql.types.ResourceRequestType")

    class Arguments:
        request_id = graphene.ID(required=True)
        reason = graphene.String(required=True)

    def mutate(self, info, request_id, reason):
        user = info.context.user
        if not user.is_authenticated or user.role != "Admin":
            raise GraphQLError("Only admins can deny requests.")

        try:
            req = ResourceRequest.objects.get(id=request_id)
        except ResourceRequest.DoesNotExist:
            raise GraphQLError("Request not found.")

        if req.status.lower() != "pending":
            raise GraphQLError("This request has already been reviewed.")

        req.status = "denied"
        req.admin_note = reason.strip()
        req.reviewed_by = user
        req.reviewed_at = timezone.now()
        req.save()

        # ✅ Notify requester (responder)
        notify_users(
            title=f"Resource Request #{req.id} Denied",
            message=f"Your request for {req.quantity} units of '{req.resource.name}' was denied. Reason: {reason}",
            users=[req.requester],
            severity="warning",
        )

        return DenyResourceRequest(
            success=True,
            message=f"Request #{req.id} denied successfully.",
            request=req,
        )



# ============================================================
# 6️⃣ ROOT MUTATION
# ============================================================



class ResourceMutation(graphene.ObjectType):
    # CRUD
    create_resource = CreateResource.Field()
    update_resource = UpdateResource.Field()
    delete_resource = DeleteResource.Field()

    # Inventory
    add_inventory = AddInventory.Field()

    # Deployment
    deploy_resource = DeployResource.Field()
    update_deployment_status = UpdateDeploymentStatus.Field()

    # Units
    change_unit_status = ChangeUnitStatus.Field()
    batch_assign_units = BatchAssignUnits.Field()

    # Requests
    create_resource_request = CreateResourceRequest.Field()
    review_resource_request = ReviewResourceRequest.Field()
    approve_resource_request = ApproveResourceRequest.Field()
    deny_resource_request = DenyResourceRequest.Field()
