


import graphene
from graphene_django import DjangoObjectType
from disaster_management.apps.users.models import User


class UserType(DjangoObjectType):
    full_name = graphene.String()

    class Meta:
        model = User
        fields = (
            "id",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "role",  
            "is_verified",
            "is_active",
            "created_at",
        )

    def resolve_full_name(self, info):
        return f"{self.first_name} {self.last_name}"