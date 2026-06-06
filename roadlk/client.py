from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import requests

from google_routes.polyline import decode_polyline

ROADLK_BASE_URL = "https://road-lk.org/api/v1"
DEFAULT_CORRIDOR_METERS = 8_000
CRITICAL_DAMAGE_TYPES = {
    "washout",
    "bridge_collapse",
    "collapse",
    "road_breakage",
    "landslide",
}


@lru_cache(maxsize=8)
def _get_json(path: str) -> Any:
    response = requests.get(f"{ROADLK_BASE_URL}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def route_to_geojson(route: dict[str, Any]) -> dict[str, Any]:
    if route.get("route_geojson"):
        return route["route_geojson"]

    encoded_polyline = route.get("polyline")
    if not encoded_polyline:
        raise ValueError("Route does not contain polyline or route_geojson.")

    decoded_points = decode_polyline(encoded_polyline)
    return {
        "type": "LineString",
        "coordinates": [[point["lng"], point["lat"]] for point in decoded_points],
    }


def _build_bbox_from_route_geometry(
    route_geojson: dict[str, Any],
    *,
    padding_degrees: float = 0.02,
) -> dict[str, float]:
    coordinates = route_geojson.get("coordinates", [])
    if not coordinates:
        raise ValueError("Route geometry does not contain coordinates.")

    longitudes = [point[0] for point in coordinates]
    latitudes = [point[1] for point in coordinates]

    return {
        "min_lat": min(latitudes) - padding_degrees,
        "min_lon": min(longitudes) - padding_degrees,
        "max_lat": max(latitudes) + padding_degrees,
        "max_lon": max(longitudes) + padding_degrees,
    }


def _distance_meters(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    lat1, lon1 = point_a
    lat2, lon2 = point_b
    radius = 6_371_000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def _route_points_latlon(route_geojson: dict[str, Any]) -> list[tuple[float, float]]:
    coordinates = route_geojson.get("coordinates", [])
    if not coordinates:
        raise ValueError("Route geometry does not contain coordinates.")
    return [(point[1], point[0]) for point in coordinates]


def _filter_incidents_for_bbox(
    incidents: list[dict[str, Any]],
    bbox: dict[str, float],
) -> list[dict[str, Any]]:
    filtered = []
    for incident in incidents:
        lat = incident.get("latitude")
        lon = incident.get("longitude")
        if lat is None or lon is None:
            continue
        if (
            bbox["min_lat"] <= lat <= bbox["max_lat"]
            and bbox["min_lon"] <= lon <= bbox["max_lon"]
        ):
            filtered.append(incident)
    return filtered


def _distance_to_route_meters(
    incident_lat: float,
    incident_lon: float,
    route_points: list[tuple[float, float]],
) -> float:
    incident_point = (incident_lat, incident_lon)
    return min(_distance_meters(incident_point, route_point) for route_point in route_points)


def _filter_incidents_for_route_corridor(
    incidents: list[dict[str, Any]],
    route_geojson: dict[str, Any],
    *,
    corridor_meters: float = DEFAULT_CORRIDOR_METERS,
) -> list[dict[str, Any]]:
    route_points = _route_points_latlon(route_geojson)
    filtered = []

    for incident in incidents:
        lat = incident.get("latitude")
        lon = incident.get("longitude")
        if lat is None or lon is None:
            continue

        distance_to_route = _distance_to_route_meters(lat, lon, route_points)
        if distance_to_route <= corridor_meters:
            incident_with_distance = dict(incident)
            incident_with_distance["distance_to_route_meters"] = round(distance_to_route, 1)
            filtered.append(incident_with_distance)

    return filtered


def _incident_priority_score(incident: dict[str, Any]) -> float:
    score = 0.0

    damage_type = incident.get("damageType")
    status = incident.get("status")
    passability = incident.get("passabilityLevel")
    blocked_distance = incident.get("blockedDistanceMeters") or 0
    distance_to_route = incident.get("distance_to_route_meters", 999999)

    if status == "resolved":
        score -= 20
    elif status == "in_progress":
        score += 20
    elif status == "verified":
        score += 12

    if passability == "unpassable":
        score += 50
    elif passability in {"foot", "car", "bus"}:
        score += 8

    if damage_type in {"washout", "bridge_collapse", "collapse"}:
        score += 35
    elif damage_type in {"road_breakage", "landslide"}:
        score += 25
    elif damage_type in {"flooding", "tree_fall"}:
        score += 12

    score += min(blocked_distance / 20, 30)
    score += max(0, 20 - distance_to_route / 1000)
    return round(score, 1)


def _is_critical_incident(incident: dict[str, Any]) -> bool:
    status = incident.get("status")
    damage_type = incident.get("damageType")
    passability = incident.get("passabilityLevel")
    blocked_distance = incident.get("blockedDistanceMeters") or 0

    if status == "resolved":
        return False
    if passability == "unpassable":
        return True
    if damage_type in {"washout", "bridge_collapse", "road_breakage"}:
        return True
    if damage_type in {"collapse", "landslide"} and blocked_distance >= 50:
        return True
    return False


def _deduplicate_incidents(
    incidents: list[dict[str, Any]],
    *,
    distance_threshold_meters: float = 750,
) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []

    for incident in incidents:
        lat = incident.get("latitude")
        lon = incident.get("longitude")
        road_location = incident.get("roadLocation")
        if lat is None or lon is None:
            deduplicated.append(incident)
            continue

        duplicate_found = False
        for kept in deduplicated:
            kept_lat = kept.get("latitude")
            kept_lon = kept.get("longitude")
            if kept_lat is None or kept_lon is None:
                continue
            same_road = kept.get("roadLocation") == road_location
            nearby = (
                _distance_meters((lat, lon), (kept_lat, kept_lon))
                <= distance_threshold_meters
            )
            if same_road and nearby:
                duplicate_found = True
                break

        if not duplicate_found:
            deduplicated.append(incident)

    return deduplicated


def _compute_risk_level(incidents: list[dict[str, Any]]) -> str:
    if not incidents:
        return "low"

    critical_count = 0
    for incident in incidents:
        status = incident.get("status")
        damage_type = incident.get("damageType")
        passability = incident.get("passabilityLevel")
        if status == "resolved":
            continue
        if passability == "unpassable" or damage_type in CRITICAL_DAMAGE_TYPES:
            critical_count += 1

    if critical_count >= 3:
        return "high"
    if critical_count >= 1 or len(incidents) >= 5:
        return "medium"
    return "low"


def get_road_alerts_for_route(route: dict[str, Any]) -> dict[str, Any]:
    route_geojson = route_to_geojson(route)
    incidents = _get_json("/map/incidents")
    last_updated = _get_json("/map/last-updated")
    bbox = _build_bbox_from_route_geometry(route_geojson)
    bbox_incidents = _filter_incidents_for_bbox(incidents, bbox)
    nearby_incidents = _filter_incidents_for_route_corridor(
        bbox_incidents,
        route_geojson,
    )
    deduplicated_incidents = _deduplicate_incidents(nearby_incidents)
    ranked_incidents = sorted(
        deduplicated_incidents,
        key=lambda incident: _incident_priority_score(incident),
        reverse=True,
    )
    critical_incidents = [
        incident for incident in ranked_incidents if _is_critical_incident(incident)
    ]

    by_status: dict[str, int] = {}
    by_damage_type: dict[str, int] = {}
    summarized_incidents = []

    for incident in ranked_incidents:
        status = incident.get("status", "unknown")
        damage_type = incident.get("damageType", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_damage_type[damage_type] = by_damage_type.get(damage_type, 0) + 1

    for incident in ranked_incidents[:12]:
        summarized_incidents.append(
            {
                "report_number": incident.get("reportNumber"),
                "road_location": incident.get("roadLocation"),
                "district": incident.get("districtName"),
                "province": incident.get("provinceName"),
                "damage_type": incident.get("damageType"),
                "status": incident.get("status"),
                "passability_level": incident.get("passabilityLevel"),
                "blocked_distance_meters": incident.get("blockedDistanceMeters"),
                "distance_to_route_meters": incident.get("distance_to_route_meters"),
                "priority_score": _incident_priority_score(incident),
                "latitude": incident.get("latitude"),
                "longitude": incident.get("longitude"),
            }
        )

    return {
        "last_updated": last_updated.get("lastUpdated"),
        "bbox": bbox,
        "total_in_bbox": len(bbox_incidents),
        "total_near_route": len(nearby_incidents),
        "total_deduplicated": len(deduplicated_incidents),
        "critical_count": len(critical_incidents),
        "risk_level": _compute_risk_level(deduplicated_incidents),
        "by_status": by_status,
        "by_damage_type": by_damage_type,
        "corridor_meters": DEFAULT_CORRIDOR_METERS,
        "critical_incidents": [
            {
                "report_number": incident.get("reportNumber"),
                "road_location": incident.get("roadLocation"),
                "district": incident.get("districtName"),
                "province": incident.get("provinceName"),
                "damage_type": incident.get("damageType"),
                "status": incident.get("status"),
                "passability_level": incident.get("passabilityLevel"),
                "blocked_distance_meters": incident.get("blockedDistanceMeters"),
                "distance_to_route_meters": incident.get("distance_to_route_meters"),
                "priority_score": _incident_priority_score(incident),
                "latitude": incident.get("latitude"),
                "longitude": incident.get("longitude"),
            }
            for incident in critical_incidents[:6]
        ],
        "incidents": summarized_incidents,
    }
