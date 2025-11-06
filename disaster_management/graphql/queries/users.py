

import graphene
from graphql import GraphQLError

from disaster_management.apps.core.utils import log_activity
from disaster_management.apps.users.models import User
from django.db.models import Q

import django_filters

from disaster_management.graphql.types.users import UserType


class UserFilter(django_filters.FilterSet):
    role = django_filters.CharFilter(method='filter_by_role')
    is_verified = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = User
        fields = ['is_verified', 'is_active']

    def filter_by_role(self, queryset, name, value):
        return queryset.filter(role__iexact=value)
    
    
class MeQuery(graphene.ObjectType):
    me = graphene.Field(UserType)

    def resolve_me(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("You must be logged in to access your profile.")
        
        log_activity(
            user=user,
            action="read",
            model_name="User",
            object_id=str(user.id),
            description="Queried their own profile via 'me' query.",
        )

        return user

class UserQuery(graphene.ObjectType):
    users = graphene.List(UserType, role=graphene.String(), is_verified=graphene.Boolean(), is_active=graphene.Boolean())
    
    
    
    def resolve_users(self, info, role=None, is_verified=None, is_active=None):
        queryset = User.objects.all()
        if role:
            queryset = queryset.filter(role__iexact=role)
        if is_verified is not None:
            queryset = queryset.filter(is_verified=is_verified)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset
    

   
class ResponderQuery(graphene.ObjectType):
    responders = graphene.List(
        UserType,
        search=graphene.String(required=False),
        is_active=graphene.Boolean(required=False),
    )

    def resolve_responders(self, info, search=None, is_active=True):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        # ✅ Only Admins can list responders
        if user.role != "Admin":
            raise GraphQLError("Only admins can view responders.")

        queryset = User.objects.filter(role="Responder")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone_number__icontains=search)
            )

        return queryset.order_by("first_name", "last_name")
    
class UsersQuery(UserQuery, MeQuery, ResponderQuery, graphene.ObjectType):
    pass