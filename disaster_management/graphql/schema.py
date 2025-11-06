import graphene

from disaster_management.graphql.mutations.forecast import ForecastMutation
from disaster_management.graphql.mutations.incidents import IncidentMutation
from disaster_management.graphql.mutations.notifications import NotificationMutation
from disaster_management.graphql.mutations.resources import ResourceMutation
from disaster_management.graphql.mutations.score_incident import AIMutation
from disaster_management.graphql.mutations.shelter import ShelterMutation
from disaster_management.graphql.mutations.users import UserMutation
from disaster_management.graphql.mutations.weather import WeatherMutation
from disaster_management.graphql.queries.core import LogsQuery
from disaster_management.graphql.queries.forecast import ForecastQuery
from disaster_management.graphql.queries.incidents import IncidentsQuery
from disaster_management.graphql.queries.notifications import NotificationsQuery
from disaster_management.graphql.queries.resources import ResourcesQuery
from disaster_management.graphql.queries.shelter import SheltersQuery
from disaster_management.graphql.queries.users import UsersQuery
from disaster_management.graphql.queries.weather import WeatherQuery


# Import queries and mutations from each module


# You can add more modules as you create them:
# from graphql.queries.incidents import IncidentQuery
# from graphql.mutations.incidents import IncidentMutation

class Query(
    UsersQuery,
    IncidentsQuery,
    SheltersQuery,
    ResourcesQuery,
    NotificationsQuery,
    WeatherQuery,
    ForecastQuery,
    LogsQuery,
    graphene.ObjectType
):
    # This base class now includes all sub-queries
    pass

class Mutation(
    UserMutation,
    IncidentMutation,
    ShelterMutation,
    ResourceMutation,
    NotificationMutation,
    WeatherMutation,
    ForecastMutation,
    AIMutation,
    graphene.ObjectType
):
    # This base class now includes all sub-mutations
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
