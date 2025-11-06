def resolve_point_field(point):
    if point:
        return {
            "latitude": point.y,
            "longitude": point.x,
        }
    return None