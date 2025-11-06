import graphene
from graphql import GraphQLError
from graphene_file_upload.scalars import Upload
from django.contrib.gis.geos import Point
from disaster_management.apps.core.utils import log_activity
from disaster_management.apps.incidents.models import Incident, IncidentComment, IncidentMedia, IncidentType
from disaster_management.apps.users.models import User
from disaster_management.graphql.types.incidents import IncidentCommentType, IncidentTypeNode
from decimal import Decimal
from graphene_file_upload.scalars import Upload

from disaster_management.utils.notifications import notify_users


class SubmitIncident(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    incident = graphene.Field(IncidentTypeNode)

    class Arguments:
        incident_type_id = graphene.ID(required=True)
        description = graphene.String(required=True)
        latitude = graphene.Float(required=True)
        longitude = graphene.Float(required=True)
        media_files = graphene.List(Upload, required=False)

    def mutate(self, info, incident_type_id, description, latitude, longitude, media_files=None):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("Authentication required to report an incident.")

        try:
            incident_type = IncidentType.objects.get(id=incident_type_id)
        except IncidentType.DoesNotExist:
            raise GraphQLError("Invalid incident type selected.")

        try:
            latitude = Decimal(str(latitude))
            longitude = Decimal(str(longitude))
            point = Point(float(longitude), float(latitude))
        except Exception:
            raise GraphQLError("Invalid latitude or longitude values.")

        incident = Incident.objects.create(
            user=user,
            incident_type=incident_type,
            description=description,
            location=point,
        )

        if media_files:
            for file in media_files:
                if not file:
                    continue
                IncidentMedia.objects.create(incident=incident, media_file=file)

        log_activity(
            user=user,
            action="create",
            model_name="Incident",
            object_id=str(incident.id),
            description=f"Reported new incident {incident.id}",
        )

        # ✅ Notify admins + responders
        admins = User.objects.filter(role="Admin")
        responders = User.objects.filter(role="Responder")
        notify_users(
            title="New Incident Reported",
            message=f"A new incident ({incident_type.name}) was reported by {user.email}.",
            users=list(admins) + list(responders),
            severity="critical",
        )

        return SubmitIncident(
            success=True,
            message="Incident reported successfully.",
            incident=incident,
        )
        
        
class AddIncidentComment(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    comment = graphene.Field(IncidentCommentType)

    class Arguments:
        incident_id = graphene.ID(required=True)
        comment = graphene.String(required=True)

    def mutate(self, info, incident_id, comment):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        try:
            incident = Incident.objects.get(id=incident_id)
        except Incident.DoesNotExist:
            raise GraphQLError("Incident not found.")

        new_comment = IncidentComment.objects.create(
            incident=incident,
            user=user,
            comment=comment.strip(),
        )

        log_activity(
            user=user,
            action="create",
            model_name="IncidentComment",
            object_id=str(new_comment.id),
            description=f"Added comment on incident {incident.id}"
        )

        # ✅ Notify Admins, Responder, and Incident Reporter
        notify_list = []
        if incident.assigned_responder:
            notify_list.append(incident.assigned_responder)
        notify_list.append(incident.user)
        notify_list += list(User.objects.filter(role="Admin"))

        notify_users(
            title="New Incident Comment",
            message=f"{user.email} commented on Incident #{incident.id}: “{comment[:80]}...”",
            users=notify_list,
            severity="info",
        )

        return AddIncidentComment(
            success=True,
            message="Comment added successfully.",
            comment=new_comment,
        )


class ChangeIncidentStatus(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    incident = graphene.Field(IncidentTypeNode)

    class Arguments:
        incident_id = graphene.ID(required=True)
        status = graphene.String(required=True)  # "pending", "responding", "resolved"

    def mutate(self, info, incident_id, status):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        if user.role not in ["Admin", "Responder"]:
            raise GraphQLError("Only Admins or Responders can change status.")

        try:
            incident = Incident.objects.get(id=incident_id)
        except Incident.DoesNotExist:
            raise GraphQLError("Incident not found.")

        if status not in ["pending", "responding", "resolved"]:
            raise GraphQLError("Invalid status value.")

        previous_status = incident.status
        incident.status = status
        incident.save()

        log_activity(
            user=user,
            action="update",
            model_name="Incident",
            object_id=str(incident.id),
            description=f"Changed status from '{previous_status}' to '{status}'"
        )

        # ✅ Notify reporter + admins + responders
        admins = User.objects.filter(role="Admin")
        responders = User.objects.filter(role="Responder")

        notify_users(
            title=f"Incident #{incident.id} Status Changed",
            message=f"Incident status changed from '{previous_status}' → '{status}' by {user.email}.",
            users=list(admins) + list(responders) + [incident.user],
            severity="info",
        )

        return ChangeIncidentStatus(
            success=True,
            message=f"Incident status updated to '{status}'.",
            incident=incident,
        )

class UpdateIncident(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    incident = graphene.Field("disaster_management.graphql.types.IncidentTypeNode")

    class Arguments:
        incident_id = graphene.ID(required=True)
        incident_type_id = graphene.ID(required=False)
        description = graphene.String(required=False)
        latitude = graphene.Float(required=False)
        longitude = graphene.Float(required=False)
        risk_score = graphene.Float(required=False)
        status = graphene.String(required=False)
        media_files = graphene.List(Upload, required=False)

    def mutate(self, info, incident_id, **kwargs):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("You must be logged in to update incidents.")

        try:
            incident = Incident.objects.get(id=incident_id)
        except Incident.DoesNotExist:
            raise GraphQLError("Incident not found.")

        is_admin = user.role == "Admin"
        is_responder = user.role == "Responder"
        is_owner = incident.user == user

        if not (is_admin or is_responder or is_owner):
            raise GraphQLError("You are not allowed to edit this incident.")

        if is_owner and not is_admin:
            restricted = {"risk_score", "status"}
            if any(field in kwargs for field in restricted):
                raise GraphQLError("You are not allowed to change status or risk score.")

        if (incident_type_id := kwargs.get("incident_type_id")) and (is_admin or is_responder):
            try:
                incident.incident_type = IncidentType.objects.get(id=incident_type_id)
            except IncidentType.DoesNotExist:
                raise GraphQLError("Invalid incident type.")

        if "description" in kwargs:
            incident.description = kwargs["description"]

        if "latitude" in kwargs and "longitude" in kwargs:
            try:
                lat = float(kwargs["latitude"])
                lng = float(kwargs["longitude"])
                incident.location = Point(lng, lat)
            except (ValueError, TypeError):
                raise GraphQLError("Invalid coordinates provided.")

        if "risk_score" in kwargs and is_admin:
            try:
                incident.risk_score = Decimal(str(kwargs["risk_score"]))
            except (ValueError, TypeError):
                raise GraphQLError("Invalid value for risk score.")

        if "status" in kwargs and is_admin:
            status = kwargs["status"]
            if status not in ["pending", "responding", "resolved"]:
                raise GraphQLError("Invalid status value.")
            incident.status = status

        incident.save()

        if media_files := kwargs.get("media_files"):
            for file in media_files:
                IncidentMedia.objects.create(incident=incident, media_file=file)

        log_activity(
            user=user,
            action="update",
            model_name="Incident",
            object_id=str(incident.id),
            description=f"Updated incident {incident.id}",
        )

        # ✅ Notify admins + reporter + assigned responder
        recipients = list(User.objects.filter(role="Admin"))
        if incident.assigned_responder:
            recipients.append(incident.assigned_responder)
        recipients.append(incident.user)

        notify_users(
            title=f"Incident #{incident.id} Updated",
            message=f"Incident '{incident.incident_type.name}' was updated by {user.email}.",
            users=recipients,
            severity="info",
        )

        return UpdateIncident(
            success=True,
            message="Incident updated successfully.",
            incident=incident,
        )

class AssignResponder(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    incident = graphene.Field(IncidentTypeNode)

    class Arguments:
        incident_id = graphene.ID(required=True)
        responder_id = graphene.ID(required=True)

    def mutate(self, info, incident_id, responder_id):
        user = info.context.user
        if not user.is_authenticated or user.role != "Admin":
            raise GraphQLError("Only admins can assign responders.")

        try:
            incident = Incident.objects.get(id=incident_id)
        except Incident.DoesNotExist:
            raise GraphQLError("Incident not found.")

        try:
            responder = User.objects.get(id=responder_id, role="Responder")
        except User.DoesNotExist:
            raise GraphQLError("Responder not found or invalid role.")

        incident.assigned_responder = responder
        incident.save()

        log_activity(
            user=user,
            action="update",
            model_name="Incident",
            object_id=str(incident.id),
            description=f"Assigned responder {responder.email} to incident {incident.id}"
        )

        # ✅ Notify responder + reporter + admins
        admins = User.objects.filter(role="Admin")
        notify_users(
            title="Responder Assigned",
            message=f"Responder {responder.email} has been assigned to Incident #{incident.id}.",
            users=list(admins) + [responder, incident.user],
            severity="info",
        )

        return AssignResponder(success=True, message="Responder assigned successfully.", incident=incident)

class DeleteIncident(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        incident_id = graphene.ID(required=True)

    def mutate(self, info, incident_id):
        user = info.context.user
        if not user.is_authenticated or user.role != "Admin":
            raise GraphQLError("Only admins can delete incidents.")

        try:
            incident = Incident.objects.get(id=incident_id)
            incident_name = incident.incident_type.name
            incident.delete()

            # ✅ Notify admins + reporter + responder
            admins = User.objects.filter(role="Admin")
            recipients = list(admins)
            if incident.assigned_responder:
                recipients.append(incident.assigned_responder)
            recipients.append(incident.user)

            notify_users(
                title="Incident Deleted",
                message=f"Incident '{incident_name}' was deleted by {user.email}.",
                users=recipients,
                severity="warning",
            )

            return DeleteIncident(success=True, message="Incident deleted successfully.")
        except Incident.DoesNotExist:
            raise GraphQLError("Incident not found.")

class IncidentMutation(graphene.ObjectType):
    submit_incident = SubmitIncident.Field()
    add_incident_comment = AddIncidentComment.Field()   
    change_incident_status = ChangeIncidentStatus.Field()
    update_incident = UpdateIncident.Field()
    assign_responder = AssignResponder.Field()
    delete_incident = DeleteIncident.Field()