import graphene
from graphql import GraphQLError
from django.contrib.gis.geos import Point

from disaster_management.apps.shelters.models import Shelter, ShelterType
from disaster_management.apps.users.models import User
from disaster_management.graphql.types.shelters import ShelterNode
from disaster_management.utils.notifications import notify_users

class CreateOrUpdateShelter(graphene.Mutation):
    shelter = graphene.Field(ShelterNode)
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        id = graphene.ID(required=False)
        name = graphene.String(required=True)
        description = graphene.String(required=False)
        shelter_type_id = graphene.ID(required=True)
        capacity = graphene.Int(required=True)
        current_occupants = graphene.Int(required=False)
        latitude = graphene.Float(required=True)
        longitude = graphene.Float(required=True)
        manager_id = graphene.ID(required=False)
        is_active = graphene.Boolean(required=False)

    def mutate(
        self,
        info,
        name,
        shelter_type_id,
        capacity,
        latitude,
        longitude,
        id=None,
        description="",
        current_occupants=0,
        manager_id=None,
        is_active=True,
    ):
        user = info.context.user
        if not user.is_authenticated or user.role != "Admin":
            raise GraphQLError("Only Admins can manage shelters.")

        try:
            shelter_type = ShelterType.objects.get(id=shelter_type_id)
        except ShelterType.DoesNotExist:
            raise GraphQLError("Invalid shelter type.")

        manager = None
        if manager_id:
            try:
                manager = User.objects.get(id=manager_id)
            except User.DoesNotExist:
                raise GraphQLError("Manager not found.")

        location = Point(longitude, latitude, srid=4326)

        if id:
            # ✅ Update existing
            try:
                shelter = Shelter.objects.get(id=id)
            except Shelter.DoesNotExist:
                raise GraphQLError("Shelter not found.")

            shelter.name = name
            shelter.description = description
            shelter.shelter_type = shelter_type
            shelter.capacity = capacity
            shelter.current_occupants = current_occupants
            shelter.location = location
            shelter.manager = manager
            shelter.is_active = is_active
            shelter.save()
            msg = "Shelter updated successfully."

            # ✅ Notify manager + responders + admins
            admins = User.objects.filter(role="Admin")
            responders = User.objects.filter(role="Responder")
            notify_list = list(admins) + list(responders)
            if manager:
                notify_list.append(manager)

            notify_users(
                title="Shelter Updated",
                message=f"Shelter '{shelter.name}' has been updated by {user.email}. Capacity: {capacity}, Occupants: {current_occupants}.",
                users=notify_list,
                severity="info",
            )

        else:
            # ✅ Create new
            shelter = Shelter.objects.create(
                name=name,
                description=description,
                shelter_type=shelter_type,
                capacity=capacity,
                current_occupants=current_occupants,
                location=location,
                manager=manager,
                is_active=is_active,
            )
            msg = "Shelter created successfully."

            # ✅ Notify responders + admins + manager
            admins = User.objects.filter(role="Admin")
            responders = User.objects.filter(role="Responder")
            notify_list = list(admins) + list(responders)
            if manager:
                notify_list.append(manager)

            notify_users(
                title="New Shelter Created",
                message=f"A new shelter '{shelter.name}' ({shelter_type.name}) has been established by {user.email}. Capacity: {capacity}.",
                users=notify_list,
                severity="info",
            )

        return CreateOrUpdateShelter(success=True, message=msg, shelter=shelter)


# ============================================================
# 2️⃣ UPDATE MY LOCATION
# ============================================================

class UpdateMyLocation(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        latitude = graphene.Float(required=True)
        longitude = graphene.Float(required=True)

    def mutate(self, info, latitude, longitude):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        point = Point(longitude, latitude, srid=4326)
        user.location = point
        user.save()

        from disaster_management.apps.shelters.models import LocationLog
        LocationLog.objects.create(user=user, location=point)

        return UpdateMyLocation(success=True, message="Location updated.")


# ============================================================
# 3️⃣ DEACTIVATE / ACTIVATE SHELTER
# ============================================================

class DeactivateShelter(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    shelter = graphene.Field("disaster_management.graphql.types.ShelterNode")

    class Arguments:
        shelter_id = graphene.ID(required=True)
        is_active = graphene.Boolean(required=True)

    def mutate(self, info, shelter_id, is_active):
        user = info.context.user
        if not user.is_authenticated or user.role != "Admin":
            raise GraphQLError("Only Admins can change shelter status.")

        try:
            shelter = Shelter.objects.get(id=shelter_id)
        except Shelter.DoesNotExist:
            raise GraphQLError("Shelter not found.")

        shelter.is_active = is_active
        shelter.save()

        status_label = "activated" if is_active else "deactivated"

        # ✅ Notify admins + responders + manager
        admins = User.objects.filter(role="Admin")
        responders = User.objects.filter(role="Responder")
        notify_list = list(admins) + list(responders)
        if shelter.manager:
            notify_list.append(shelter.manager)

        notify_users(
            title=f"Shelter {status_label.title()}",
            message=f"Shelter '{shelter.name}' has been {status_label} by {user.email}.",
            users=notify_list,
            severity="warning" if not is_active else "info",
        )

        return DeactivateShelter(
            success=True,
            message=f"Shelter {status_label} successfully.",
            shelter=shelter,
        )



class ShelterMutation(graphene.ObjectType):
    create_or_update_shelter = CreateOrUpdateShelter.Field()
    update_my_location = UpdateMyLocation.Field()
    deactivate_shelter = DeactivateShelter.Field()