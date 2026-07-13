from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any


_LEVEL_RANK = {"unknown": -1, "low": 0, "medium": 1, "high": 2}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _level(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    if normalized in {"good", "clear", "best"}:
        return "low"
    if normalized in {"moderate", "caution"}:
        return "medium"
    if normalized in _LEVEL_RANK:
        return normalized
    return "unknown"


def _highest_level(*levels: Any) -> str:
    normalized = [_level(level) for level in levels]
    known = [level for level in normalized if level != "unknown"]
    return max(known, key=lambda item: _LEVEL_RANK[item]) if known else "unknown"


def _place_name(place: dict[str, Any] | None, fallback: str = "Unknown place") -> str:
    place = place or {}
    return str(place.get("display_name") or place.get("name") or fallback)


def _selected_attractions(segment: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = (
        segment.get("gemini_selected_attractions")
        or segment.get("selected_attractions")
        or segment.get("top_attractions")
        or []
    )
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    for attraction in candidates:
        if not isinstance(attraction, dict):
            continue
        key = str(
            attraction.get("place_id")
            or attraction.get("id")
            or _place_name(attraction)
        ).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append(attraction)
    return selected[:3]


def _coordinates(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    location = value.get("location") if isinstance(value.get("location"), dict) else value
    lat = _number(_first_present(location, "lat", "latitude"))
    lng = _number(_first_present(location, "lng", "lon", "longitude"))
    if lat is None or lng is None:
        return None
    return lat, lng


def _distance_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(radians, first)
    lat2, lon2 = map(radians, second)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    haversine = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(haversine))


def _segment_points(segment: dict[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for value in segment.get("segment_path_points") or []:
        point = _coordinates(value)
        if point:
            points.append(point)
    if points:
        return points
    for key in ("start_point", "mid_point", "end_point"):
        point = _coordinates(segment.get(key))
        if point:
            points.append(point)
    return points


def _assign_incidents_to_days(
    incidents: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> tuple[dict[int, list[dict[str, Any]]], int]:
    assigned = {int(segment.get("day") or index): [] for index, segment in enumerate(segments, start=1)}
    segment_points = {
        int(segment.get("day") or index): _segment_points(segment)
        for index, segment in enumerate(segments, start=1)
    }
    unlocated = 0
    for incident in incidents:
        point = _coordinates(incident)
        if point is None:
            unlocated += 1
            continue
        distances = [
            (min(_distance_m(point, route_point) for route_point in points), day)
            for day, points in segment_points.items()
            if points
        ]
        if not distances:
            unlocated += 1
            continue
        _distance, day = min(distances)
        assigned.setdefault(day, []).append(incident)
    return assigned, unlocated


def _weather_condition(code: Any) -> str | None:
    value = _number(code)
    if value is None:
        return None
    code_value = int(value)
    if code_value in {0, 1000}:
        return "Clear"
    if code_value in {1, 2, 1003}:
        return "Partly cloudy"
    if code_value in {3, 1006, 1009}:
        return "Cloudy"
    if code_value in {45, 48, 1030, 1135, 1147}:
        return "Fog or mist"
    if 51 <= code_value <= 57 or code_value in {1150, 1153, 1168, 1171}:
        return "Drizzle"
    if 61 <= code_value <= 67 or 1180 <= code_value <= 1201:
        return "Rain"
    if 71 <= code_value <= 77 or 1210 <= code_value <= 1237:
        return "Snow"
    if 80 <= code_value <= 82 or 1240 <= code_value <= 1246:
        return "Rain showers"
    if code_value in {85, 86, 1255, 1258}:
        return "Snow showers"
    if 95 <= code_value <= 99 or 1273 <= code_value <= 1282:
        return "Thunderstorms"
    return "Mixed conditions"


def _forecast_value(forecast: dict[str, Any], field: str, date: str | None, fallback_index: int) -> Any:
    values = forecast.get(field)
    if not isinstance(values, list) or not values:
        return None
    dates = forecast.get("dates") or []
    index = fallback_index
    if date and date in dates:
        index = dates.index(date)
    if 0 <= index < len(values):
        return values[index]
    return None


def _weather_payload(segment: dict[str, Any], date: str | None, day_index: int) -> dict[str, Any]:
    weather = segment.get("weather") or {}
    forecast = weather.get("forecast") or {}
    risk = weather.get("risk") or {}
    if forecast.get("status") == "unavailable" or not forecast:
        return {
            "status": "unavailable",
            "condition": "Forecast unavailable",
            "risk_level": _level(risk.get("risk_level")),
            "risk_score": _number(risk.get("score")),
            "reasons": risk.get("reasons") or [],
            "guidance": "Recheck the forecast closer to this day.",
        }

    code = _forecast_value(forecast, "weather_codes", date, day_index)
    if code is None:
        code = _forecast_value(forecast, "weather_code", date, day_index)
    rain_probability = _number(
        _forecast_value(forecast, "precipitation_probability_max", date, day_index)
    )
    rain_mm = _number(_forecast_value(forecast, "precipitation_sum", date, day_index))
    risk_level = _level(risk.get("risk_level"))
    if risk_level == "unknown" and rain_probability is not None:
        risk_level = "high" if rain_probability >= 70 else "medium" if rain_probability >= 40 else "low"
    guidance = "Conditions look manageable for the planned stops."
    if risk_level == "high":
        guidance = "Keep outdoor stops flexible and prepare an indoor fallback if conditions worsen."
    elif risk_level == "medium":
        guidance = "Carry rain cover and leave timing flexibility between outdoor stops."

    return {
        "status": forecast.get("status") or "ok",
        "condition": _weather_condition(code) or "Forecast available",
        "weather_code": code,
        "temperature_max_c": _number(_forecast_value(forecast, "temperature_max", date, day_index)),
        "temperature_min_c": _number(_forecast_value(forecast, "temperature_min", date, day_index)),
        "rain_probability_pct": rain_probability,
        "rainfall_mm": rain_mm,
        "wind_speed_kph": _number(_forecast_value(forecast, "wind_speed_max", date, day_index)),
        "risk_level": risk_level,
        "risk_score": _number(risk.get("score")),
        "reasons": risk.get("reasons") or [],
        "guidance": guidance,
    }


def _day_pressure(crowd_signals: dict[str, Any], day: int) -> dict[str, Any]:
    zone_pressure = crowd_signals.get("zone_pressure") or {}
    for item in zone_pressure.get("days") or []:
        if int(item.get("day") or 0) == day:
            return item
    return {
        "day": day,
        "pressure_score": crowd_signals.get("signal_score"),
        "pressure_level": crowd_signals.get("risk_level") or "unknown",
        "reasons": [],
    }


def _attraction_pressure_index(crowd_signals: dict[str, Any], day: int) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in crowd_signals.get("attraction_pressure") or []:
        item_day = int(item.get("day") or day)
        if item_day != day:
            continue
        for value in (item.get("place_id"), item.get("name"), item.get("display_name")):
            if value:
                index[str(value).strip().lower()] = item
    return index


def _is_indoor(attraction: dict[str, Any]) -> bool:
    values = [
        *(attraction.get("types") or []),
        *(attraction.get("categories") or []),
        attraction.get("primary_type"),
    ]
    text = " ".join(str(value or "").lower() for value in values)
    return any(token in text for token in ("museum", "gallery", "shopping", "indoor", "temple", "church"))


def _attraction_payloads(
    segment: dict[str, Any],
    day_pressure: dict[str, Any],
    crowd_signals: dict[str, Any],
    weather: dict[str, Any],
) -> list[dict[str, Any]]:
    day = int(segment.get("day") or 0)
    pressure_index = _attraction_pressure_index(crowd_signals, day)
    payloads: list[dict[str, Any]] = []
    for attraction in _selected_attractions(segment):
        name = _place_name(attraction, "Attraction")
        exact = None
        for key in (attraction.get("place_id"), attraction.get("id"), name):
            if key and str(key).strip().lower() in pressure_index:
                exact = pressure_index[str(key).strip().lower()]
                break
        crowd = exact or day_pressure
        crowd_level = _level(crowd.get("pressure_level") or crowd.get("combined_pressure"))
        recommended_window = (
            crowd.get("best_visit_window")
            or crowd.get("preferred_visit_window")
            or day_pressure.get("preferred_visit_window")
            or "Keep timing flexible"
        )
        recommended_time = (
            recommended_window.get("label")
            if isinstance(recommended_window, dict)
            else recommended_window
        )
        action = f"Visit {name} during {str(recommended_time).replace('_', ' ')}."
        if crowd_level == "high":
            action = f"Prioritize {name} early and avoid its busiest period where possible."
        elif weather.get("risk_level") in {"medium", "high"} and not _is_indoor(attraction):
            action = f"Keep {name} flexible because it is an outdoor stop and weather may disrupt timing."
        payloads.append(
            {
                "place_id": attraction.get("place_id") or attraction.get("id"),
                "name": name,
                "district": attraction.get("district"),
                "rating": _number(attraction.get("rating")),
                "types": attraction.get("types") or attraction.get("categories") or [],
                "crowd": {
                    "score": _number(_first_present(crowd, "pressure_score", "combined_score")),
                    "level": crowd_level,
                    "source": "attraction_estimate" if exact else "day_estimate",
                    "reasons": crowd.get("reasons") or [],
                    "best_visit_window": recommended_time,
                    "wiki_interest": crowd.get("wiki_interest") if exact else None,
                },
                "weather_suitability": {
                    "level": "protected" if _is_indoor(attraction) else weather.get("risk_level"),
                    "reason": (
                        "Indoor or sheltered stop."
                        if _is_indoor(attraction)
                        else weather.get("guidance")
                    ),
                },
                "recommended_time": recommended_time,
                "action": action,
            }
        )
    return payloads


def _lodging_price(lodging: dict[str, Any]) -> float | None:
    for key in (
        "total_price_lkr",
        "price_lkr",
        "current_price_lkr",
        "estimated_nightly_cost_lkr",
        "price",
    ):
        value = _number(lodging.get(key))
        if value is not None and value > 0:
            return value
    return None


def _lodging_payload(segment: dict[str, Any]) -> dict[str, Any] | None:
    if segment.get("is_overnight_stop") is False:
        return None
    lodging = segment.get("recommended_lodging")
    if not isinstance(lodging, dict) or not lodging:
        return None
    price = _lodging_price(lodging)
    return {
        "place_id": lodging.get("place_id") or lodging.get("id"),
        "name": _place_name(lodging, "Selected stay"),
        "location": lodging.get("district") or lodging.get("formatted_address"),
        "rating": _number(lodging.get("rating")),
        "price_lkr": price,
        "price_label": f"LKR {price:,.0f}" if price is not None else "Price unavailable",
    }


def _transport_by_day(plan: dict[str, Any]) -> dict[int, float]:
    transport = plan.get("transport_cost") or (plan.get("route_data") or {}).get("transport_cost") or {}
    result: dict[int, float] = {}
    for index, segment in enumerate(transport.get("segments") or [], start=1):
        day = int(segment.get("day") or index)
        value = _number(segment.get("estimated_fare_lkr"))
        if value is not None:
            result[day] = value
    return result


def _road_level(incidents: list[dict[str, Any]]) -> str:
    if not incidents:
        return "low"
    for incident in incidents:
        text = " ".join(
            str(incident.get(key) or "").lower()
            for key in ("status", "passability_level", "damage_type", "priority_score")
        )
        if any(token in text for token in ("blocked", "impassable", "critical", "high")):
            return "high"
    return "medium"


def _road_payload(
    incidents: list[dict[str, Any]],
    road_alerts: dict[str, Any],
    unlocated_count: int,
) -> dict[str, Any]:
    level = _road_level(incidents)
    incident_payloads = [
        {
            "report_number": item.get("report_number"),
            "location": item.get("road_location") or item.get("district") or "Location unavailable",
            "district": item.get("district"),
            "damage_type": item.get("damage_type") or "Road incident",
            "status": item.get("status") or "unknown",
            "passability": item.get("passability_level"),
            "distance_to_route_meters": _number(item.get("distance_to_route_meters")),
            "latitude": _number(item.get("latitude")),
            "longitude": _number(item.get("longitude")),
        }
        for item in incidents
    ]
    guidance = "No geolocated RoadLK incidents are assigned to this day's route segment."
    if incident_payloads:
        first = incident_payloads[0]
        guidance = f"Allow extra time near {first['location']} due to {first['damage_type'].lower()}."
    return {
        "risk_level": level,
        "route_alert_count": len(incident_payloads),
        "critical_count": sum(1 for item in incidents if _road_level([item]) == "high"),
        "route_wide_unlocated_count": unlocated_count,
        "last_updated": road_alerts.get("last_updated"),
        "incidents": incident_payloads,
        "guidance": guidance,
    }


def _day_recommendations(
    attractions: list[dict[str, Any]],
    weather: dict[str, Any],
    roads: dict[str, Any],
    lodging: dict[str, Any] | None,
) -> list[str]:
    recommendations = [item["action"] for item in attractions[:2]]
    if weather.get("risk_level") in {"medium", "high"}:
        recommendations.append(weather["guidance"])
    if roads.get("route_alert_count"):
        recommendations.append(roads["guidance"])
    if lodging:
        recommendations.append(f"Finish the day near {lodging['name']} ({lodging['price_label']}).")
    if not recommendations:
        recommendations.append("Conditions are manageable; keep the planned route order and normal timing buffers.")
    return recommendations[:4]


def _fallback_plan(attractions: list[dict[str, Any]], weather: dict[str, Any]) -> str:
    if weather.get("risk_level") not in {"medium", "high"}:
        return "No special fallback is required; keep one short rest break available."
    sheltered = next(
        (item for item in attractions if item.get("weather_suitability", {}).get("level") == "protected"),
        None,
    )
    if sheltered:
        return f"If weather worsens, move {sheltered['name']} earlier and shorten exposed outdoor stops."
    return "If weather worsens, shorten exposed outdoor stops and use a nearby indoor cultural stop."


def build_daily_briefings(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a factual, frontend-ready briefing for each already-selected route day."""
    recommended_route = plan.get("recommended_route") or {}
    segments = recommended_route.get("segments") or (plan.get("route_data") or {}).get("segments") or []
    trip_dates = plan.get("trip_dates") or []
    crowd_signals = plan.get("crowd_signals") or recommended_route.get("crowd_signals") or {}
    road_alerts = plan.get("road_alerts") or recommended_route.get("road_alerts") or {}
    incidents = [item for item in road_alerts.get("incidents") or [] if isinstance(item, dict)]
    incidents_by_day, unlocated_count = _assign_incidents_to_days(incidents, segments)
    transport_by_day = _transport_by_day(plan)
    destination = _place_name(plan.get("destination_resolved"), "the destination")

    briefings: list[dict[str, Any]] = []
    for index, segment in enumerate(segments, start=1):
        day = int(segment.get("day") or index)
        date = trip_dates[day - 1] if day - 1 < len(trip_dates) else None
        day_pressure = _day_pressure(crowd_signals, day)
        weather = _weather_payload(segment, date, day - 1)
        attractions = _attraction_payloads(segment, day_pressure, crowd_signals, weather)
        roads = _road_payload(incidents_by_day.get(day, []), road_alerts, unlocated_count)
        lodging = _lodging_payload(segment)
        stay_cost = lodging.get("price_lkr") if lodging else 0
        transport_cost = transport_by_day.get(day, 0)
        districts = day_pressure.get("districts") or []
        location_label = (
            ", ".join(str(item) for item in districts[:2])
            or day_pressure.get("corridor")
            or (destination if day == len(segments) else f"route segment {day}")
        )
        crowd_level = _level(day_pressure.get("pressure_level") or crowd_signals.get("risk_level"))
        day_pressure_score = _first_present(day_pressure, "pressure_score")
        crowd_score = _number(
            day_pressure_score
            if day_pressure_score is not None
            else crowd_signals.get("signal_score")
        )
        overall_status = _highest_level(crowd_level, weather.get("risk_level"), roads.get("risk_level"))
        condition_parts = [f"crowds are {crowd_level}" if crowd_level != "unknown" else "crowd data is limited"]
        condition_parts.append(
            f"weather risk is {weather.get('risk_level')}"
            if weather.get("risk_level") != "unknown"
            else "weather risk is unknown"
        )
        condition_parts.append(
            f"road risk is {roads.get('risk_level')}"
            if roads.get("risk_level") != "unknown"
            else "road risk is unknown"
        )
        distance_m = _number(segment.get("segment_distance_m"))
        distance_km = _number(segment.get("segment_distance_km"))
        if distance_km is None and distance_m is not None:
            distance_km = round(distance_m / 1000, 1)

        briefings.append(
            {
                "day": day,
                "date": date,
                "title": f"Day {day} - {location_label}",
                "location_label": location_label,
                "overall_status": overall_status,
                "summary": f"Around {location_label}, {', '.join(condition_parts)}.",
                "route": {
                    "distance_km": distance_km,
                    "duration_seconds": segment.get("segment_duration_seconds"),
                    "start_point": segment.get("start_point"),
                    "end_point": segment.get("end_point"),
                },
                "weather": weather,
                "crowd": {
                    "risk_level": crowd_level,
                    "score": crowd_score,
                    "preferred_visit_window": day_pressure.get("preferred_visit_window"),
                    "reasons": day_pressure.get("reasons") or [],
                    "components": day_pressure.get("components") or {},
                },
                "attractions": attractions,
                "roads": roads,
                "accommodation": lodging,
                "costs": {
                    "accommodation_lkr": stay_cost or 0,
                    "estimated_transport_lkr": transport_cost or 0,
                    "tracked_total_lkr": (stay_cost or 0) + (transport_cost or 0),
                    "excludes": ["attraction entry fees", "meals", "personal spending", "flight cost"],
                },
                "recommendations": _day_recommendations(attractions, weather, roads, lodging),
                "fallback_plan": _fallback_plan(attractions, weather),
            }
        )
    return briefings
