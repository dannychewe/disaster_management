import graphene
from graphene_django.converter import convert_django_field
from django.contrib.gis.db.models import PointField

@convert_django_field.register(PointField)
def convert_point_field_to_string(field, registry=None):
    return graphene.String()
