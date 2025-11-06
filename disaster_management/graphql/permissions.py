# disaster_management/graphql/permissions.py
from functools import wraps
from graphql import GraphQLError
from graphql_jwt.decorators import login_required

def role_required(*allowed_roles):
    def decorator(resolver):
        @wraps(resolver)
        @login_required
        def wrapper(self, info, *args, **kwargs):
            user = info.context.user
            if user.is_anonymous:
                raise GraphQLError("Authentication required.")
            if user.role not in allowed_roles:
                raise GraphQLError("Access denied.")
            return resolver(self, info, *args, **kwargs)
        return wrapper
    return decorator
