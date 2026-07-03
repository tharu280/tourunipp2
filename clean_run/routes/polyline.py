from __future__ import annotations

import math
from typing import Any


def decode_polyline(encoded: str) -> list[dict[str, float]]:
    """Decode a Google encoded polyline into latitude/longitude points."""
    index = 0
    latitude = 0
    longitude = 0
    coordinates: list[dict[str, float]] = []

    while index < len(encoded):
        latitude_change, index = _decode_value(encoded, index)
        longitude_change, index = _decode_value(encoded, index)
        latitude += latitude_change
        longitude += longitude_change
        coordinates.append(
            {
                "lat": latitude / 1e5,
                "lng": longitude / 1e5,
            }
        )

    return coordinates


def _decode_value(encoded: str, index: int) -> tuple[int, int]:
    shift = 0
    result = 0

    while True:
        value = ord(encoded[index]) - 63
        index += 1
        result |= (value & 0x1F) << shift
        shift += 5
        if value < 0x20:
            break

    decoded = ~(result >> 1) if result & 1 else result >> 1
    return decoded, index


def haversine_meters(point_a: dict[str, float], point_b: dict[str, float]) -> float:
    radius_m = 6_371_000
    lat1 = math.radians(point_a["lat"])
    lon1 = math.radians(point_a["lng"])
    lat2 = math.radians(point_b["lat"])
    lon2 = math.radians(point_b["lng"])

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_m * c


def cumulative_distances(points: list[dict[str, float]]) -> list[float]:
    distances = [0.0]
    for index in range(1, len(points)):
        segment = haversine_meters(points[index - 1], points[index])
        distances.append(distances[-1] + segment)
    return distances


def point_at_distance(
    points: list[dict[str, float]],
    cumulative: list[float],
    target_distance_m: float,
) -> dict[str, float]:
    if not points:
        raise ValueError("Cannot select a point from an empty route.")
    if target_distance_m <= 0:
        return points[0]
    if target_distance_m >= cumulative[-1]:
        return points[-1]

    for index in range(1, len(points)):
        start_distance = cumulative[index - 1]
        end_distance = cumulative[index]
        if target_distance_m <= end_distance:
            span = end_distance - start_distance
            if span <= 0:
                return points[index]
            fraction = (target_distance_m - start_distance) / span
            start_point = points[index - 1]
            end_point = points[index]
            return {
                "lat": start_point["lat"]
                + (end_point["lat"] - start_point["lat"]) * fraction,
                "lng": start_point["lng"]
                + (end_point["lng"] - start_point["lng"]) * fraction,
            }

    return points[-1]


def sample_route_points(points: list[dict[str, float]], *, max_points: int = 200) -> list[dict[str, float]]:
    if len(points) <= max_points:
        return points

    step = max(1, len(points) // max_points)
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def summarize_geometry(encoded_polyline: str) -> dict[str, Any]:
    decoded_points = decode_polyline(encoded_polyline)
    cumulative = cumulative_distances(decoded_points)
    total_distance_m = cumulative[-1] if cumulative else 0.0

    return {
        "point_count": len(decoded_points),
        "sampled_points": sample_route_points(decoded_points),
        "total_geometry_distance_m": round(total_distance_m, 2),
        "decoded_points": decoded_points,
        "cumulative_distances_m": cumulative,
    }


# Approximate metres per degree at Sri Lanka's latitude (~7°N).
# Used only for corridor deviation; haversine_meters is used for exact distances.
_M_PER_DEG_LAT: float = 111_320.0
_M_PER_DEG_LNG: float = 96_050.0  # 111_320 * cos(7°)


def max_corridor_deviation_m(
    route_points: list[dict[str, float]],
    *,
    origin: dict[str, float],
    destination: dict[str, float],
) -> float:
    """Return the maximum perpendicular deviation (metres) of any route point
    from the direct origin-destination corridor.

    Uses a 2D approximation in scaled lat/lng space, which is accurate enough
    for Sri Lanka (error < 2 % for distances under 500 km).

    Returns 0.0 if fewer than 2 points are given or origin == destination.
    """
    if not route_points or not origin or not destination:
        return 0.0

    # Convert to approximate metres in a flat 2D plane.
    ax = origin["lat"] * _M_PER_DEG_LAT
    ay = origin["lng"] * _M_PER_DEG_LNG
    bx = destination["lat"] * _M_PER_DEG_LAT
    by = destination["lng"] * _M_PER_DEG_LNG

    dx = bx - ax
    dy = by - ay
    segment_len_sq = dx * dx + dy * dy

    if segment_len_sq < 1.0:
        # Origin and destination are essentially the same point.
        return 0.0

    max_deviation = 0.0
    for pt in route_points:
        px = pt["lat"] * _M_PER_DEG_LAT
        py = pt["lng"] * _M_PER_DEG_LNG

        # Perpendicular distance from point P to the infinite line through A→B.
        cross = abs(dx * (ay - py) - dy * (ax - px))
        perp_dist = cross / math.sqrt(segment_len_sq)

        if perp_dist > max_deviation:
            max_deviation = perp_dist

    return max_deviation
