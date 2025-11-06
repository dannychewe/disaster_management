import graphene
from graphql import GraphQLError

from disaster_management.apps.forecasting.models import ForecastModel
from disaster_management.apps.forecasting.tasks import run_flood_prediction, run_drought_prediction


class RunManualForecast(graphene.Mutation):
    message = graphene.String()

    class Arguments:
        model_id = graphene.ID(required=True)

    def mutate(self, info, model_id):
        try:
            model = ForecastModel.objects.get(id=model_id)
        except ForecastModel.DoesNotExist:
            raise GraphQLError("Forecast model not found.")

        if model.model_type == "flood":
            run_flood_prediction.delay()
        elif model.model_type == "drought":
            run_drought_prediction.delay()
        else:
            raise GraphQLError(f"Unsupported forecast type: {model.model_type}")

        return RunManualForecast(message=f"{model.name} forecast triggered successfully.")


class ForecastMutation(graphene.ObjectType):
    run_manual_forecast = RunManualForecast.Field()