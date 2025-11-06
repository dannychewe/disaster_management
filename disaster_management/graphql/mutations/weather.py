import graphene
from graphql import GraphQLError
from disaster_management.apps.weather.tasks import (
    calculate_risk_zones,
    pull_weather_data,
)


class PullWeatherData(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    @classmethod
    def mutate(cls, root, info):
        pull_weather_data.delay()
        return PullWeatherData(success=True, message="Weather data pulling triggered.")


class RecalculateRiskZones(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    @classmethod
    def mutate(cls, root, info):
        calculate_risk_zones.delay()
        return RecalculateRiskZones(success=True, message="Risk zone recalculation triggered.")


class WeatherMutation(graphene.ObjectType):
    recalculate_risk_zones = RecalculateRiskZones.Field()
    pull_weather_data = PullWeatherData.Field()
