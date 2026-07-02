from __future__ import annotations

from typing import Any
import requests

from clean_run.integrations.weather_client import (
    fetch_weather_for_point,
    summarize_daily_weather,
    weather_risk_score,
)


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

    try:
        raw_forecast = fetch_weather_for_point(
            latitude=point["lat"],
            longitude=point["lng"],
            start_date=trip_dates[0],
            end_date=trip_dates[-1],
        )
        forecast = summarize_daily_weather(raw_forecast)
        risk = weather_risk_score(forecast, day_index=day_index)
    except requests.RequestException as exc:
        forecast = {
            "status": "unavailable",
            "error": f"weather request failed: {exc}",
        }
        risk = {
            "score": None,
            "risk_level": "unknown",
            "reasons": ["Weather forecast unavailable because the provider request failed."],
        }

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
