from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from graphene_django.views import GraphQLView
from django.conf import settings
from django.conf.urls.static import static
from graphene_file_upload.django import FileUploadGraphQLView
from graphql_jwt.decorators import jwt_cookie

urlpatterns = [
    path('admin/', admin.site.urls),

    # GraphQL endpoint
    path("graphql/", csrf_exempt(FileUploadGraphQLView.as_view(graphiql=True)))
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
