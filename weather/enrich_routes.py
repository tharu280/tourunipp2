from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from weather.client import (
    build_trip_dates,
    fetch_weather_for_point,
    summarize_daily_weather,
    weather_risk_score,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich saved route files with weather summaries per route and day segment."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a saved routes or enriched-routes JSON file.",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Trip start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--trip-days",
        type=int,
        default=None,
        help="Trip duration in whole days. If omitted, tries to read it from the input file.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. Defaults to outputs/weather-enriched-<timestamp>.json",
    )
    return parser.parse_args()


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs") / f"weather-enriched-routes-{timestamp}.json"


def infer_trip_days(payload: dict[str, Any], explicit_trip_days: int | None) -> int:
    if explicit_trip_days is not None:
        return max(explicit_trip_days, 1)
    payload_days = payload.get("trip_days")
    if isinstance(payload_days, int) and payload_days > 0:
        return payload_days
    return 1


def enrich_segment_weather(
    *,
    segment: dict[str, Any],
    trip_dates: list[str],
    day_index: int,
) -> dict[str, Any]:
    point = segment.get("mid_point") or segment.get("end_point") or segment.get("start_point")
    if not point:
        return {
            **segment,
            "weather": {
                "forecast": {"status": "unavailable"},
                "risk": {
                    "score": None,
                    "risk_level": "unknown",
                    "reasons": ["Segment points unavailable."],
                },
            },
        }

    raw_forecast = fetch_weather_for_point(
        latitude=point["lat"],
        longitude=point["lng"],
        start_date=trip_dates[0],
        end_date=trip_dates[-1],
    )
    forecast = summarize_daily_weather(raw_forecast)
    risk = weather_risk_score(forecast, day_index=day_index)

    return {
        **segment,
        "weather": {
            "anchor_point": point,
            "forecast": forecast,
            "risk": risk,
        },
    }


def route_weather_summary(segments: list[dict[str, Any]]) -> dict[str, Any]:
    scored_segments = [
        segment["weather"]["risk"]["score"]
        for segment in segments
        if segment.get("weather", {}).get("risk", {}).get("score") is not None
    ]
    if not scored_segments:
        return {
            "average_weather_risk_score": None,
            "max_weather_risk_score": None,
            "risk_level": "unknown",
        }

    average_score = round(sum(scored_segments) / len(scored_segments), 2)
    max_score = max(scored_segments)

    if max_score >= 60 or average_score >= 50:
        risk_level = "high"
    elif max_score >= 30 or average_score >= 20:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "average_weather_risk_score": average_score,
        "max_weather_risk_score": max_score,
        "risk_level": risk_level,
    }


def enrich_route(
    *,
    route: dict[str, Any],
    trip_dates: list[str],
) -> dict[str, Any]:
    if not route.get("segments"):
        return {
            **route,
            "weather_summary": {
                "average_weather_risk_score": None,
                "max_weather_risk_score": None,
                "risk_level": "unknown",
            },
        }

    enriched_segments = []
    for day_index, segment in enumerate(route.get("segments", [])):
        enriched_segments.append(
            enrich_segment_weather(
                segment=segment,
                trip_dates=trip_dates,
                day_index=day_index,
            )
        )

    return {
        **route,
        "segments": enriched_segments,
        "weather_summary": route_weather_summary(enriched_segments),
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    trip_days = infer_trip_days(payload, args.trip_days)
    trip_dates = build_trip_dates(args.start_date, trip_days)

    enriched_routes = [
        enrich_route(route=route, trip_dates=trip_dates)
        for route in payload.get("routes", [])
    ]

    output = {
        **payload,
        "trip_days": trip_days,
        "trip_dates": trip_dates,
        "weather_enriched_at_utc": datetime.now(timezone.utc).isoformat(),
        "routes": enriched_routes,
    }

    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved weather-enriched routes to {output_path}")


if __name__ == "__main__":
    main()
