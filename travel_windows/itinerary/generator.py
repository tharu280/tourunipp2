from __future__ import annotations

from typing import Any

from gemini_refine.client import generate_markdown_text


def _segment_selected_attractions(segment: dict[str, Any]) -> list[dict[str, Any]]:
    selected = segment.get("gemini_selected_attractions") or []
    if selected:
        return selected
    return (segment.get("top_attractions") or [])[:3]


def _route_alternative_advice(
    *,
    routes: list[dict[str, Any]],
    recommended_route: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not recommended_route:
        return []

    advice = []
    recommended_id = recommended_route.get("route_id")
    recommended_crowd = ((recommended_route.get("crowd_signals") or {}).get("signal_score")) or 0
    recommended_road = ((recommended_route.get("road_alerts") or {}).get("critical_count")) or 0

    for route in routes:
        route_id = route.get("route_id")
        if route_id == recommended_id:
            continue

        route_crowd = ((route.get("crowd_signals") or {}).get("signal_score")) or 0
        route_road = ((route.get("road_alerts") or {}).get("critical_count")) or 0
        route_distance = float(route.get("distance_meters") or 0)
        recommended_distance = float(recommended_route.get("distance_meters") or 0)

        if route_crowd + 8 < recommended_crowd:
            advice.append(
                {
                    "type": "route_alternative",
                    "route_id": route_id,
                    "title": f"Route {route_id} may feel less crowded",
                    "message": (
                        f"{route_id} shows a lower travel-pressure score than the currently selected route "
                        "for this trip window."
                    ),
                }
            )
        elif route_road + 1 < recommended_road:
            advice.append(
                {
                    "type": "route_alternative",
                    "route_id": route_id,
                    "title": f"Route {route_id} may reduce route-side disruption",
                    "message": f"{route_id} currently carries fewer critical road alerts than the selected route.",
                }
            )
        elif route_distance <= recommended_distance * 1.1 and route_crowd <= recommended_crowd:
            advice.append(
                {
                    "type": "route_alternative",
                    "route_id": route_id,
                    "title": f"Route {route_id} remains a viable fallback",
                    "message": "Keep this route in reserve if conditions tighten around the selected corridor.",
                }
            )
    return advice[:3]


def build_itinerary_guidance(plan: dict[str, Any]) -> dict[str, Any]:
    crowd_signals = plan.get("crowd_signals") or {}
    travel_windows = plan.get("travel_windows") or {}
    routes = plan.get("routes") or []
    recommended_route = plan.get("recommended_route") or {}
    route_options = _route_alternative_advice(routes=routes, recommended_route=recommended_route)

    return {
        "summary": crowd_signals.get("helper_summary", "No crowd guidance summary is available."),
        "recommendations": crowd_signals.get("recommendations", []),
        "redistribution_suggestions": crowd_signals.get("redistribution_suggestions", []),
        "best_windows": travel_windows.get("best_windows", []),
        "worst_windows": travel_windows.get("worst_windows", []),
        "route_alternatives": route_options,
    }


def build_fallback_itinerary(plan: dict[str, Any], guidance: dict[str, Any]) -> str:
    route_data = plan.get("route_data") or {}
    recommended_route = plan.get("recommended_route") or {}
    road_alerts = plan.get("road_alerts") or {}
    weather_data = plan.get("weather_data") or {}
    crowd_signals = plan.get("crowd_signals") or {}
    origin = (plan.get("origin_resolved") or {}).get("name", "Origin")
    destination = (plan.get("destination_resolved") or {}).get("name", "Destination")

    lines = [
        f"# {origin} to {destination} itinerary",
        "",
        f"This route covers approximately **{route_data.get('distance_km', 'unknown')} km** with an estimated drive time of **{route_data.get('duration_str', 'unknown')}**.",
        "",
        "## Trip overview",
        f"- Selected route: **{route_data.get('route_id', 'route')}**",
        f"- Road risk: **{road_alerts.get('risk_level', 'unknown')}**",
        f"- Travel pressure: **{crowd_signals.get('risk_level', 'unknown')}**",
        f"- Weather stress: **{(weather_data.get('summary') or {}).get('risk_level', 'unknown')}**",
        "",
    ]

    best_windows = guidance.get("best_windows") or []
    if best_windows:
        lines.extend(
            [
                "## Best timing notes",
                *[
                    f"- {item['date']} {item['time_range']} is one of the strongest travel windows."
                    for item in best_windows[:2]
                ],
                "",
            ]
        )

    for segment in recommended_route.get("segments", []):
        attractions = _segment_selected_attractions(segment)
        stay = segment.get("recommended_lodging")
        weather_risk = segment.get("weather", {}).get("risk", {})
        lines.append(f"## Day {segment.get('day')}")
        lines.append(
            f"- Travel segment: **{round(float(segment.get('segment_distance_m', 0) or 0) / 1000, 1)} km** over **{int((segment.get('segment_duration_seconds') or 0) // 3600)}h {int(((segment.get('segment_duration_seconds') or 0) % 3600) // 60)}m**."
        )
        lines.append(
            f"- Expected pressure: **{weather_risk.get('risk_level', 'low')} weather risk** with route crowd guidance layered in."
        )
        if attractions:
            lines.append("- Suggested attractions:")
            for attraction in attractions[:3]:
                lines.append(
                    f"  - **{attraction.get('display_name', 'Attraction')}** in {attraction.get('district', 'the corridor')} — {attraction.get('summary', 'worth visiting on this route day.')}"
                )
        else:
            lines.append("- Suggested attractions: keep this day lighter and use it mainly for transfer and recovery.")
        if stay:
            lines.append(
                f"- Overnight stay: **{stay.get('display_name', 'recommended stay')}** near the day-end anchor."
            )
        lines.append("")

        segment_suggestions = [
            item for item in guidance.get("redistribution_suggestions", [])
            if item.get("day") == segment.get("day")
        ]
        if segment_suggestions:
            lines.append("### Flexibility note")
            for item in segment_suggestions[:2]:
                lines.append(f"- {item.get('message')}")
            lines.append("")

    route_alternatives = guidance.get("route_alternatives") or []
    if route_alternatives:
        lines.append("## Route fallback ideas")
        for item in route_alternatives:
            lines.append(f"- {item.get('message')}")
        lines.append("")

    return "\n".join(lines).strip()


def build_gemini_prompt(plan: dict[str, Any], guidance: dict[str, Any]) -> str:
    route_data = plan.get("route_data") or {}
    recommended_route = plan.get("recommended_route") or {}
    origin = (plan.get("origin_resolved") or {}).get("name", "Origin")
    destination = (plan.get("destination_resolved") or {}).get("name", "Destination")
    crowd = plan.get("crowd_signals") or {}
    road = plan.get("road_alerts") or {}
    weather = plan.get("weather_data") or {}

    day_blocks = []
    for segment in recommended_route.get("segments", []):
        attractions = _segment_selected_attractions(segment)
        stay = segment.get("recommended_lodging")
        redist = [
            item["message"]
            for item in guidance.get("redistribution_suggestions", [])
            if item.get("day") == segment.get("day")
        ]
        day_blocks.append(
            "\n".join(
                [
                    f"Day {segment.get('day')}:",
                    f"- Distance: {round(float(segment.get('segment_distance_m', 0) or 0) / 1000, 1)} km",
                    f"- Duration: {int((segment.get('segment_duration_seconds') or 0) // 3600)}h {int(((segment.get('segment_duration_seconds') or 0) % 3600) // 60)}m",
                    *[
                        f"- Attraction: {place.get('display_name')} ({place.get('district')}) — {place.get('summary')}"
                        for place in attractions[:4]
                    ],
                    (f"- Stay: {stay.get('display_name')}" if stay else "- Stay: no overnight recommendation"),
                    *[f"- Flexibility: {item}" for item in redist[:2]],
                ]
            )
        )

    return (
        "You are an expert Sri Lanka travel planner.\n"
        f"Create a polished day-by-day itinerary in Markdown for a trip from {origin} to {destination}.\n"
        f"Total route distance is about {route_data.get('distance_km')} km with driving time {route_data.get('duration_str')}.\n"
        f"Road risk: {road.get('risk_level', 'unknown')}. "
        f"Travel pressure: {crowd.get('risk_level', 'unknown')}. "
        f"Weather stress: {(weather.get('summary') or {}).get('risk_level', 'unknown')}.\n"
        "Use the pressure, travel-window, and redistribution guidance naturally.\n"
        "If a day looks busy, explicitly suggest a better visit time or a lower-pressure fallback.\n"
        "Keep it realistic, helpful, and tourist-friendly.\n"
        "Do not invent places outside the provided route context.\n\n"
        "Guidance summary:\n"
        f"- {guidance.get('summary', 'No extra guidance.')}\n"
        + "\n".join(f"- {item}" for item in guidance.get("recommendations", [])[:4])
        + "\n\nDay context:\n"
        + "\n\n".join(day_blocks)
    )


def build_itinerary_output(plan: dict[str, Any], *, use_gemini: bool = True) -> dict[str, Any]:
    guidance = build_itinerary_guidance(plan)
    fallback_markdown = build_fallback_itinerary(plan, guidance)

    if not use_gemini:
        return {
            "itinerary_guidance": guidance,
            "itinerary_markdown": fallback_markdown,
            "itinerary_source": "fallback",
        }

    prompt = build_gemini_prompt(plan, guidance)
    try:
        markdown = generate_markdown_text(prompt=prompt)
        return {
            "itinerary_guidance": guidance,
            "itinerary_markdown": markdown.strip(),
            "itinerary_source": "gemini",
        }
    except Exception as exc:
        guidance = {
            **guidance,
            "generation_warning": f"Gemini itinerary generation failed, so the fallback itinerary was used: {exc}",
        }
        return {
            "itinerary_guidance": guidance,
            "itinerary_markdown": fallback_markdown,
            "itinerary_source": "fallback",
        }
