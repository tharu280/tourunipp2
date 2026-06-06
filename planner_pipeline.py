from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from trip_graph.graph import invoke_trip_graph


@dataclass
class TripPlanOptions:
    include_gemini: bool = True
    include_roadlk: bool = True
    include_weather: bool = True
    include_crowd: bool = True
    place_strategy: str = "nearby"


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import threading

        result: dict[str, object] = {}
        error: dict[str, BaseException] = {}

        def runner():
            try:
                result["value"] = asyncio.run(coro)
            except BaseException as exc:  # pragma: no cover - sync bridge guard
                error["exc"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if "exc" in error:
            raise error["exc"]
        return result.get("value")

    return asyncio.run(coro)


def save_plan_snapshot(plan: dict[str, Any], *, output_dir: str | Path = "outputs") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = Path(output_dir) / f"streamlit-trip-plan-{timestamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        __import__("json").dumps(plan, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def build_plan_text_export(plan: dict[str, Any]) -> str:
    route_data = plan.get("route_data") or {}
    crowd = plan.get("crowd_signals") or {}
    road = plan.get("road_alerts") or {}
    weather = (plan.get("weather_data") or {}).get("summary") or {}
    recommended_route = plan.get("recommended_route") or {}
    origin = (plan.get("origin_resolved") or {}).get("name") or "Origin"
    destination = (plan.get("destination_resolved") or {}).get("name") or "Destination"
    trip_dates = plan.get("trip_dates") or []
    itinerary_markdown = (plan.get("itinerary_markdown") or "").strip()

    lines = [
        "TOUR INTELLIGENCE PLAN",
        "",
        f"Origin: {origin}",
        f"Destination: {destination}",
        f"Route ID: {route_data.get('route_id', '—')}",
        f"Distance: {route_data.get('distance_str') or route_data.get('summary') or '—'}",
        f"Drive time: {route_data.get('duration_str', '—')}",
        f"Trip dates: {trip_dates[0]} to {trip_dates[-1]}" if trip_dates else "Trip dates: —",
        f"Road risk: {road.get('risk_level', 'unknown')}",
        f"Travel pressure: {crowd.get('risk_level', 'unknown')}",
        f"Weather stress: {weather.get('risk_level', 'unknown')}",
        "",
        "DAY SUMMARY",
        "",
    ]

    for segment in recommended_route.get("segments", []) or []:
        day_label = segment.get("day_label", f"Day {segment.get('day')}")
        weather_risk = (segment.get("weather", {}).get("risk") or {}).get("risk_level", "unknown")
        attractions = (
            segment.get("gemini_selected_attractions")
            or segment.get("selected_attractions")
            or segment.get("top_attractions")
            or []
        )
        stays = segment.get("top_lodging") or []
        lines.extend(
            [
                f"{day_label}",
                f"- Segment distance: {round(float(segment.get('segment_distance_m', 0) or 0) / 1000, 1)} km",
                f"- Segment duration: {int((segment.get('segment_duration_seconds') or 0) // 3600)}h {int(((segment.get('segment_duration_seconds') or 0) % 3600) // 60)}m",
                f"- Weather risk: {weather_risk}",
            ]
        )
        if attractions:
            lines.append("- Attractions:")
            for attraction in attractions[:5]:
                lines.append(f"  - {attraction.get('display_name', 'Attraction')} ({attraction.get('district', 'corridor')})")
        else:
            lines.append("- Attractions: none selected")
        if segment.get("is_overnight_stop"):
            if stays:
                lines.append("- Accommodation:")
                for stay in stays[:3]:
                    lines.append(f"  - {stay.get('display_name', 'Stay')} ({stay.get('price_band', 'stay')})")
            else:
                lines.append("- Accommodation: none selected")
        lines.append("")

    if itinerary_markdown:
        lines.extend(
            [
                "FINAL ITINERARY",
                "",
                itinerary_markdown,
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def save_plan_text_export(plan: dict[str, Any], *, output_dir: str | Path = "outputs") -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamped = output_path / f"streamlit-trip-plan-{timestamp}.txt"
    latest = output_path / "latest-trip-plan.txt"
    text = build_plan_text_export(plan)

    timestamped.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    return timestamped, latest


def build_trip_plan(
    *,
    origin_text: str,
    destination_text: str,
    duration_text: str,
    start_date: date,
    departure_time: str = "08:00",
    options: TripPlanOptions | None = None,
) -> dict[str, Any]:
    active_options = options or TripPlanOptions()
    return _run_async(
        invoke_trip_graph(
            origin_text=origin_text,
            destination_text=destination_text,
            duration_text=duration_text,
            start_date=start_date,
            departure_time=departure_time,
            options=active_options,
        )
    )
