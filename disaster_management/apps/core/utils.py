


from .models import ActivityLog


def log_activity(user, action, model_name, object_id=None, description=""):

    ActivityLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=object_id,
        description=description
    )
    
    
    
    