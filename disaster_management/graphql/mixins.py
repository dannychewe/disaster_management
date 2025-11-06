from graphene import Field, Float, JSONString, ObjectType

class LocationType(ObjectType):
    latitude = Float()
    longitude = Float()

class PolygonCoordinatesType(ObjectType):
    coordinates = Field(lambda: [[ [Float()] ]])  # 3D: multi-ring polygons

class LocationResolverMixin:
    def resolve_location(self, info):
        if hasattr(self, 'location') and self.location:
            return LocationType(latitude=self.location.y, longitude=self.location.x)
        return None

class DestinationResolverMixin:
    def resolve_destination(self, info):
        if hasattr(self, 'destination') and self.destination:
            return LocationType(latitude=self.destination.y, longitude=self.destination.x)
        return None

class GeometryResolverMixin:
    def resolve_geometry(self, info):
        if hasattr(self, 'geometry') and self.geometry:
            return PolygonCoordinatesType(coordinates=self.geometry.coords)
        return None

class GeoJSONResolverMixin:
    geojson = JSONString()

    def resolve_geojson(self, info):
        if hasattr(self, 'affected_area') and self.affected_area:
            return {
                "type": "Feature",
                "geometry": self.affected_area.geojson,
                "properties": {
                    "area_name": getattr(self, "area_name", None),
                    "risk_level": getattr(self, "risk_level", None),
                    "confidence": getattr(self, "confidence", None),
                    "forecast_date": getattr(self, "forecast_date", None).isoformat() if getattr(self, "forecast_date", None) else None,
                    "predicted_at": getattr(self, "predicted_at", None).isoformat() if getattr(self, "predicted_at", None) else None,
                    "model": self.model.name if hasattr(self, "model") and self.model else None,
                }
            }
        return None
