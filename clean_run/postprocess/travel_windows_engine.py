from __future__ import annotations

from datetime import date, datetime
from typing import Any

from clean_run.integrations.weather_client import build_trip_dates

TIME_SLOTS = [
    {"label": "Early Morning", "start": "05:00", "end": "06:30", "weekday_score": 10, "weekend_score": 8},
    {"label": "Morning Rush", "start": "06:30", "end": "09:30", "weekday_score": 28, "weekend_score": 14},
    {"label": "Late Morning", "start": "09:30", "end": "12:30", "weekday_score": 12, "weekend_score": 10},
    {"label": "Midday", "start": "12:30", "end": "14:00", "weekday_score": 14, "weekend_score": 12},
    {"label": "School Pickup", "start": "14:00", "end": "16:00", "weekday_score": 20, "weekend_score": 11},
    {"label": "Evening Rush", "start": "16:00", "end": "18:30", "weekday_score": 26, "weekend_score": 15},
    {"label": "Evening", "start": "18:30", "end": "21:00", "weekday_score": 16, "weekend_score": 14},
]


def _score_to_level(score: int) -> str:
    if score >= 72:
        return "worst"
    if score >= 52:
        return "bad"
    if score >= 34:
        return "good"
    return "best"


def _weather_by_date(weather_data: dict[str, Any]) -> dict[str, dict[str, float]]:
    per_date: dict[str, dict[str, float]] = {}
    for location in weather_data.get("locations", []):
        forecast = location.get("forecast", {})
        if forecast.get("status") != "ok":
            continue

        for day, rain_prob, rainfall, wind_speed in zip(
            forecast.get("dates", []),
            forecast.get("precipitation_probability_max", []),
            forecast.get("precipitation_sum", []),
            forecast.get("wind_speed_max", []),
        ):
            bucket = per_date.setdefault(
                day,
                {
                    "max_rain_probability": 0.0,
                    "rainfall_total": 0.0,
                    "wind_max": 0.0,
                    "samples": 0.0,
                },
            )
            bucket["max_rain_probability"] = max(bucket["max_rain_probability"], float(rain_prob or 0))
            bucket["rainfall_total"] += float(rainfall or 0)
            bucket["wind_max"] = max(bucket["wind_max"], float(wind_speed or 0))
            bucket["samples"] += 1

    for bucket in per_date.values():
        samples = bucket["samples"] or 1
        bucket["avg_rainfall"] = round(bucket["rainfall_total"] / samples, 1)
    return per_date


def _weather_score(summary: dict[str, float], slot_label: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    rain_prob = summary.get("max_rain_probability", 0.0)
    avg_rainfall = summary.get("avg_rainfall", 0.0)
    wind_max = summary.get("wind_max", 0.0)

    if rain_prob >= 80:
        score += 12
        reasons.append(f"rain probability peaks near {round(rain_prob)}%")
    elif rain_prob >= 60:
        score += 7
        reasons.append(f"rain probability is elevated at {round(rain_prob)}%")

    if avg_rainfall >= 18:
        score += 10
        reasons.append(f"average rainfall is around {avg_rainfall} mm")
    elif avg_rainfall >= 8:
        score += 5
        reasons.append(f"some rainfall is expected at about {avg_rainfall} mm")

    if wind_max >= 40:
        score += 8
        reasons.append(f"wind speeds may reach {round(wind_max)} km/h")
    elif wind_max >= 28:
        score += 4
        reasons.append(f"wind may stay noticeable at {round(wind_max)} km/h")

    if slot_label in {"School Pickup", "Evening Rush"} and rain_prob >= 60:
        score += 4
        reasons.append("wet conditions can intensify afternoon congestion")
    return score, reasons


def _road_score(road_alerts: dict[str, Any], slot_label: str) -> tuple[int, list[str]]:
    risk_level = road_alerts.get("risk_level", "unknown")
    critical_count = int(road_alerts.get("critical_count", 0) or 0)
    incident_count = int(road_alerts.get("total_deduplicated", 0) or 0)
    score = 0
    reasons: list[str] = []

    if risk_level == "high":
        score += 18
    elif risk_level == "medium":
        score += 10
    elif risk_level == "low":
        score += 4

    if critical_count:
        score += min(critical_count * 4, 14)
        reasons.append(f"{critical_count} critical RoadLK alert(s) affect the corridor")
    elif incident_count:
        score += min(incident_count * 2, 8)
        reasons.append(f"{incident_count} route-side incident(s) may slow movement")

    if slot_label in {"Morning Rush", "School Pickup", "Evening Rush"} and score:
        score += 4
        reasons.append("existing route friction is harder to absorb during busy traffic windows")
    return score, reasons


def _live_traffic_score(traffic_data: dict[str, Any], slot_label: str) -> tuple[int, list[str]]:
    if not traffic_data or traffic_data.get("status") != "ok":
        return 0, []
    score = 0
    reasons: list[str] = []
    congestion = int(traffic_data.get("congestion_score", 0) or 0)
    if slot_label in {"Morning Rush", "Late Morning"}:
        score += min(max(congestion // 4, 0), 12)
    elif slot_label in {"Early Morning", "School Pickup", "Evening Rush"}:
        score += min(max(congestion // 6, 0), 8)
    else:
        score += min(max(congestion // 10, 0), 4)

    delay_minutes = traffic_data.get("delay_minutes")
    if delay_minutes and score:
        reasons.append(f"live route traffic is adding about {round(float(delay_minutes))} minutes")
    elif score:
        reasons.append("live route traffic is slower than normal near departure")
    return score, reasons


def _calendar_score(*, iso_date: str, weekend_dates: set[str], holiday_matches: dict[str, dict[str, Any]]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if iso_date in holiday_matches:
        holiday = holiday_matches[iso_date]
        score += 22
        reasons.append(
            f"public holiday demand is elevated because of {holiday.get('local_name') or holiday.get('name') or 'a holiday'}"
        )
    if iso_date in weekend_dates:
        score += 10
        reasons.append("weekend leisure demand can add extra route pressure")
    return score, reasons


def _parse_time_hhmm(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError:
        return None
    return parsed.hour, parsed.minute


def _time_in_slot(value: str | None, slot: dict[str, Any]) -> bool:
    parsed = _parse_time_hhmm(value)
    if parsed is None:
        return False
    hour, minute = parsed
    target = hour * 60 + minute
    start_hour, start_minute = _parse_time_hhmm(slot["start"]) or (0, 0)
    end_hour, end_minute = _parse_time_hhmm(slot["end"]) or (23, 59)
    start_total = start_hour * 60 + start_minute
    end_total = end_hour * 60 + end_minute
    return start_total <= target < end_total


def build_travel_windows(
    *,
    start_date: str,
    trip_days: int,
    departure_time: str | None,
    weather_data: dict[str, Any],
    road_alerts: dict[str, Any],
    crowd_signals: dict[str, Any],
    traffic_data: dict[str, Any],
    route_data: dict[str, Any],
) -> dict[str, Any]:
    trip_dates = build_trip_dates(start_date, trip_days)
    weekend_dates = set(crowd_signals.get("weekend_dates") or [])
    holiday_matches = {
        item.get("date"): item
        for item in crowd_signals.get("holiday_matches") or []
        if item.get("date")
    }
    weather_map = _weather_by_date(weather_data)
    distance_km = float(route_data.get("distance_km", 0) or 0)

    overview_rows = []
    days = []

    for day_index, iso_date in enumerate(trip_dates, start=1):
        slot_rows = []
        weather_summary = weather_map.get(iso_date, {})
        calendar_points, calendar_reasons = _calendar_score(
            iso_date=iso_date,
            weekend_dates=weekend_dates,
            holiday_matches=holiday_matches,
        )
        parsed_day = date.fromisoformat(iso_date)
        is_weekday = parsed_day.weekday() < 5

        for slot in TIME_SLOTS:
            traffic_points = slot["weekday_score"] if is_weekday else slot["weekend_score"]
            traffic_reasons = []
            if traffic_points >= 24:
                traffic_reasons.append("commuter traffic is usually heaviest in this time band")
            elif traffic_points >= 18:
                traffic_reasons.append("this time band commonly catches school or office movement")
            elif traffic_points <= 10:
                traffic_reasons.append("this time band is usually quieter for intercity travel")

            weather_points, weather_reasons = _weather_score(weather_summary, slot["label"])
            road_points, road_reasons = _road_score(road_alerts, slot["label"])
            live_traffic_points, live_traffic_reasons = _live_traffic_score(traffic_data, slot["label"])

            long_route_bonus = 0
            long_route_reason = ""
            if distance_km >= 180 and slot["label"] in {"Morning Rush", "Evening Rush"}:
                long_route_bonus = 5
                long_route_reason = "long intercity routes feel peak-hour friction for longer"
            elif distance_km >= 120 and slot["label"] in {"School Pickup", "Evening Rush"}:
                long_route_bonus = 3
                long_route_reason = "a longer route increases exposure to late-day slowdowns"

            total_score = min(
                100,
                traffic_points + calendar_points + weather_points + road_points + live_traffic_points + long_route_bonus,
            )
            level = _score_to_level(int(total_score))
            reasons = traffic_reasons + calendar_reasons + weather_reasons + road_reasons + live_traffic_reasons
            if long_route_reason:
                reasons.append(long_route_reason)

            slot_row = {
                "label": slot["label"],
                "start_time": slot["start"],
                "end_time": slot["end"],
                "score": int(total_score),
                "level": level,
                "reasons": reasons[:4],
                "components": {
                    "traffic": traffic_points,
                    "calendar": calendar_points,
                    "weather": weather_points,
                    "road": road_points,
                    "live_traffic": live_traffic_points,
                    "route_length": long_route_bonus,
                },
                "selected_departure_match": day_index == 1 and _time_in_slot(departure_time, slot),
            }
            slot_rows.append(slot_row)
            overview_rows.append(
                {
                    "date": iso_date,
                    "day_label": f"Day {day_index}",
                    "slot_label": slot["label"],
                    "time_range": f"{slot['start']}-{slot['end']}",
                    "score": int(total_score),
                    "level": level,
                    "reasons": slot_row["reasons"],
                    "components": slot_row["components"],
                    "selected_departure_match": slot_row["selected_departure_match"],
                }
            )

        slot_rows.sort(key=lambda item: item["score"])
        best_slot = slot_rows[0]
        worst_slot = slot_rows[-1]
        days.append(
            {
                "date": iso_date,
                "day_label": f"Day {day_index}",
                "best_slot": {
                    "label": best_slot["label"],
                    "time_range": f"{best_slot['start_time']}-{best_slot['end_time']}",
                    "score": best_slot["score"],
                    "level": best_slot["level"],
                },
                "worst_slot": {
                    "label": worst_slot["label"],
                    "time_range": f"{worst_slot['start_time']}-{worst_slot['end_time']}",
                    "score": worst_slot["score"],
                    "level": worst_slot["level"],
                },
                "slots": slot_rows,
            }
        )

    sorted_rows = sorted(overview_rows, key=lambda item: item["score"])
    selected_departure = next((row for row in overview_rows if row["selected_departure_match"]), None)

    summary_bits = []
    if sorted_rows:
        summary_bits.append(f"Best window overall is {sorted_rows[0]['date']} {sorted_rows[0]['time_range']}")
        summary_bits.append(f"Worst window overall is {sorted_rows[-1]['date']} {sorted_rows[-1]['time_range']}")
    if selected_departure:
        summary_bits.append(f"Chosen departure time falls in a {selected_departure['level']} pressure window")

    return {
        "departure_time": departure_time,
        "summary": ". ".join(summary_bits) if summary_bits else "No travel window insight available.",
        "selected_departure": selected_departure,
        "best_windows": sorted_rows[:4],
        "worst_windows": list(reversed(sorted_rows[-4:])),
        "days": days,
        "chart_rows": overview_rows,
    }
