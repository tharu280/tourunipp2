from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Any


_RISK_RANK = {"unknown": 0, "low": 1, "medium": 2, "high": 3}


def _risk(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    if normalized in {"moderate", "caution"}:
        return "medium"
    return normalized if normalized in _RISK_RANK else "unknown"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if mapping.get(key) is not None:
            return mapping.get(key)
    return None


def _briefing_map(plan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for item in plan.get("daily_briefings") or []:
        try:
            day = int(item.get("day"))
        except (TypeError, ValueError):
            continue
        result[day] = item
    return result


def _first_attraction(briefing: dict[str, Any]) -> dict[str, Any]:
    attractions = briefing.get("attractions") or []
    return attractions[0] if attractions and isinstance(attractions[0], dict) else {}


def _rain_probability(weather: dict[str, Any]) -> float:
    for key in (
        "rain_probability_pct",
        "rain_probability",
        "chance_of_rain",
        "precipitation_probability",
    ):
        if weather.get(key) is not None:
            return _number(weather.get(key))
    forecast = weather.get("forecast") or {}
    for key in (
        "rain_probability_pct",
        "rain_probability",
        "chance_of_rain",
        "precipitation_probability",
    ):
        if forecast.get(key) is not None:
            return _number(forecast.get(key))
    return 0.0


def _road_alert_count(roads: dict[str, Any]) -> int:
    for key in ("active_alert_count", "alert_count", "alerts_near_route", "total_near_route"):
        if roads.get(key) is not None:
            return int(_number(roads.get(key)))
    alerts = roads.get("alerts") or roads.get("incidents") or []
    return len(alerts) if isinstance(alerts, list) else 0


def _primary_action(briefing: dict[str, Any], *, fallback: str) -> str:
    recommendations = briefing.get("recommendations") or []
    for item in recommendations:
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            text = item.get("action") or item.get("recommendation") or item.get("title")
            if text:
                return str(text).strip()
    fallback_plan = briefing.get("fallback_plan") or briefing.get("fallback")
    if isinstance(fallback_plan, str) and fallback_plan.strip():
        return fallback_plan.strip()
    if isinstance(fallback_plan, dict):
        text = fallback_plan.get("action") or fallback_plan.get("recommendation")
        if text:
            return str(text).strip()
    return fallback


def _dedupe_key(session_id: str, day: int, changes: list[dict[str, Any]]) -> str:
    signature = {
        "session_id": session_id,
        "day": day,
        "changes": [
            {
                "signal": item.get("signal"),
                "current_level": item.get("current_level"),
                "current_value": item.get("current_value"),
            }
            for item in changes
        ],
    }
    encoded = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _change_summary(signal: str, previous: str, current: str, current_value: Any = None) -> str:
    if signal == "weather" and current_value is not None:
        return f"Rain probability is now {round(_number(current_value))}% ({current} weather risk)."
    if signal == "crowd" and current_value is not None:
        return f"Relative crowd pressure is now {round(_number(current_value))}/100 ({current})."
    if signal == "roads" and current_value is not None:
        return f"Road risk is now {current} with {int(_number(current_value))} nearby alert(s)."
    return f"{signal.title()} risk changed from {previous} to {current}."


def _spoken_briefing(
    *,
    day: int,
    location: str,
    changes: list[dict[str, Any]],
    action: str,
) -> str:
    signal_summary = " ".join(
        str(item.get("summary") or "").strip()
        for item in changes
        if str(item.get("summary") or "").strip()
    )
    return (
        f"TourUni update for Day {day}, near {location}. "
        f"{signal_summary} Recommended action: {action}"
    ).strip()


def build_condition_update_events(
    *,
    session_id: str,
    previous_plan: dict[str, Any],
    current_plan: dict[str, Any],
    user_id: str | None = None,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    """Create meaningful, deduplicatable updates without mutating either plan."""
    previous_days = _briefing_map(previous_plan)
    current_days = _briefing_map(current_plan)
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    events: list[dict[str, Any]] = []

    for day in sorted(set(previous_days) & set(current_days)):
        previous = previous_days[day]
        current = current_days[day]
        changes: list[dict[str, Any]] = []

        previous_weather = previous.get("weather") or {}
        current_weather = current.get("weather") or {}
        old_weather_risk = _risk(previous_weather.get("risk_level") or previous_weather.get("risk"))
        new_weather_risk = _risk(current_weather.get("risk_level") or current_weather.get("risk"))
        old_rain = _rain_probability(previous_weather)
        new_rain = _rain_probability(current_weather)
        rain_crossed = old_rain < 70 <= new_rain
        weather_worsened = _RISK_RANK[new_weather_risk] > _RISK_RANK[old_weather_risk] and _RISK_RANK[new_weather_risk] >= 2
        if rain_crossed or weather_worsened:
            changes.append(
                {
                    "signal": "weather",
                    "previous_level": old_weather_risk,
                    "current_level": new_weather_risk,
                    "previous_value": old_rain,
                    "current_value": new_rain,
                    "summary": _change_summary("weather", old_weather_risk, new_weather_risk, new_rain),
                }
            )

        previous_crowd = previous.get("crowd") or {}
        current_crowd = current.get("crowd") or {}
        old_crowd_risk = _risk(previous_crowd.get("risk_level") or previous_crowd.get("level"))
        new_crowd_risk = _risk(current_crowd.get("risk_level") or current_crowd.get("level"))
        old_crowd_score = _number(_first_present(previous_crowd, "score", "pressure_score"))
        new_crowd_score = _number(_first_present(current_crowd, "score", "pressure_score"))
        crowd_crossed = old_crowd_score < 60 <= new_crowd_score
        crowd_worsened = _RISK_RANK[new_crowd_risk] > _RISK_RANK[old_crowd_risk] and _RISK_RANK[new_crowd_risk] >= 2
        if crowd_crossed or crowd_worsened:
            changes.append(
                {
                    "signal": "crowd",
                    "previous_level": old_crowd_risk,
                    "current_level": new_crowd_risk,
                    "previous_value": old_crowd_score,
                    "current_value": new_crowd_score,
                    "summary": _change_summary("crowd", old_crowd_risk, new_crowd_risk, new_crowd_score),
                }
            )

        previous_roads = previous.get("roads") or previous.get("road") or {}
        current_roads = current.get("roads") or current.get("road") or {}
        old_road_risk = _risk(previous_roads.get("risk_level") or previous_roads.get("level"))
        new_road_risk = _risk(current_roads.get("risk_level") or current_roads.get("level"))
        old_alerts = _road_alert_count(previous_roads)
        new_alerts = _road_alert_count(current_roads)
        road_worsened = _RISK_RANK[new_road_risk] > _RISK_RANK[old_road_risk] and _RISK_RANK[new_road_risk] >= 2
        new_road_alert = new_alerts > old_alerts and new_road_risk in {"medium", "high"}
        if road_worsened or new_road_alert:
            changes.append(
                {
                    "signal": "roads",
                    "previous_level": old_road_risk,
                    "current_level": new_road_risk,
                    "previous_value": old_alerts,
                    "current_value": new_alerts,
                    "summary": _change_summary("roads", old_road_risk, new_road_risk, new_alerts),
                }
            )

        if not changes:
            continue

        attraction = _first_attraction(current)
        attraction_name = attraction.get("name") or attraction.get("display_name")
        location = current.get("location_label") or attraction_name or f"Day {day} route"
        signals = [item["signal"] for item in changes]
        severity = "high" if any(item.get("current_level") == "high" for item in changes) else "medium"
        category = signals[0] if len(signals) == 1 else "multi_signal"
        signal_text = ", ".join(signals[:-1]) + (f" and {signals[-1]}" if len(signals) > 1 else signals[0])
        fallback_action = (
            f"Keep Day {day} flexible and review a nearby alternative before leaving for {attraction_name or location}."
        )
        action = _primary_action(current, fallback=fallback_action)
        title = f"Day {day} conditions changed"
        change_summary = " ".join(str(item["summary"]) for item in changes)
        message = f"{location} now has higher {signal_text} pressure. {change_summary}"
        speech_text = _spoken_briefing(
            day=day,
            location=str(location),
            changes=changes,
            action=action,
        )
        notification_id = str(uuid.uuid4())
        alternative_lookup = bool({"weather", "crowd"} & set(signals)) and bool(attraction_name)

        events.append(
            {
                "notification_id": notification_id,
                "dedupe_key": _dedupe_key(session_id, day, changes),
                "type": "condition_change",
                "category": category,
                "severity": severity,
                "session_id": session_id,
                "user_id": user_id,
                "day": day,
                "date": current.get("date"),
                "location_label": location,
                "attraction": {
                    "id": attraction.get("place_id") or attraction.get("id"),
                    "name": attraction_name,
                },
                "title": title,
                "message": message,
                "speech_text": speech_text,
                "changes": changes,
                "recommendation": {
                    "headline": "Recommended adjustment",
                    "action": action,
                    "alternative_search_recommended": alternative_lookup,
                    "contextual_alternatives_request": {
                        "day": day,
                        "attraction_id": attraction.get("place_id") or attraction.get("id"),
                        "force": True,
                    }
                    if alternative_lookup
                    else None,
                },
                "created_at": timestamp,
                "read": False,
                "push": {
                    "eligible": True,
                    "title": title,
                    "body": message,
                    "data": {
                        "screen": "trip_updates",
                        "session_id": session_id,
                        "notification_id": notification_id,
                        "day": day,
                    },
                },
            }
        )

    return events
