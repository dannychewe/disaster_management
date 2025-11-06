import graphene
from graphql import GraphQLError

from disaster_management.apps.ai.models import IncidentAIAnalysis
from disaster_management.apps.ai.scoring import compute_risk_score
from disaster_management.apps.incidents.models import Incident
from disaster_management.apps.users.models import User
from disaster_management.utils.notifications import notify_users
from disaster_management.apps.ai.tasks import detect_spatial_clusters


class ScoreIncident(graphene.Mutation):
    """Triggers AI risk scoring for an existing incident."""

    class Arguments:
        incident_id = graphene.ID(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    risk_score = graphene.Float()
    label = graphene.String()

    def mutate(self, info, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            raise GraphQLError("Incident not found.")

        # --- Run the AI scoring locally or via FastAPI helper ---
        result = compute_risk_score(incident)

        ai_analysis, _ = IncidentAIAnalysis.objects.update_or_create(
            incident=incident,
            defaults={
                "risk_score": result["risk_score"],
                "confidence": result["confidence"],
                "label": result["label"],
                "drivers": result["drivers"],
                "version": result["version"],
            },
        )

        # --- Update main Incident fields ---
        incident.risk_score = result["risk_score"]
        incident.risk_label = result["label"]
        incident.risk_confidence = result["confidence"]
        incident.risk_drivers = result["drivers"]
        incident.ai_version = result["version"]
        incident.save(update_fields=[
            "risk_score", "risk_label", "risk_confidence",
            "risk_drivers", "ai_version"
        ])

        # --- Send notification if risk is high ---
        if result["risk_score"] >= 75:
            admins = User.objects.filter(role__in=["Admin", "Responder"], is_active=True)
            message = (
                f"A new {incident.incident_type.get_name_display()} incident "
                f"was scored HIGH RISK ({result['risk_score']:.1f}/100).\n\n"
                f"Location: ({incident.location.y:.4f}, {incident.location.x:.4f})\n"
                f"{result.get('explanation', 'Please review immediately.')}"
            )
            notify_users(
                title="⚠️ High-Risk Incident Detected",
                message=message,
                users=list(admins),
                severity="critical",
            )

        # --- Trigger cluster detection asynchronously ---
        detect_spatial_clusters.delay(incident.id)

        return ScoreIncident(
            success=True,
            message=result.get("explanation", "Risk analysis completed."),
            risk_score=result["risk_score"],
            label=result["label"],
        )


class AIMutation(graphene.ObjectType):
    score_incident = ScoreIncident.Field()
