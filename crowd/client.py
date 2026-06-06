from __future__ import annotations

from collections import defaultdict
from datetime import date
from functools import lru_cache
from typing import Any
import json

import requests

from weather.client import build_trip_dates

NAGER_BASE_URL = "https://date.nager.at/api/v3"
SRI_LANKA_COUNTRY_CODE = "LK"

OUTDOOR_CATEGORIES = {
    "nature",
    "waterfall",
    "beach",
    "wildlife",
    "scenic",
    "adventure",
}

OUTDOOR_TAGS = {
    "day_trip",
    "photography",
    "beachfront",
    "mountain_view",
    "wildlife_access",
    "scenic",
}

CROWD_SENSITIVE_TAGS = {
    "must_see",
    "iconic",
    "family_friendly",
    "unesco",
}

CORRIDOR_RULES = [
    ("Hill Country Corridor", {"Kandy", "Matale", "Nuwara Eliya", "Badulla", "Monaragala"}),
    ("South Coast Corridor", {"Colombo", "Kalutara", "Galle", "Matara", "Hambantota"}),
    ("Cultural Triangle Corridor", {"Anuradhapura", "Polonnaruwa", "Matale", "Kurunegala"}),
    ("East Coast Corridor", {"Trincomalee", "Batticaloa", "Ampara"}),
    ("Northern Corridor", {"Jaffna", "Mannar", "Kilinochchi", "Mullaitivu", "Vavuniya"}),
]


@lru_cache(maxsize=8)
def _get_public_holidays(year: int) -> list[dict[str, Any]]:
    response = requests.get(
        f"{NAGER_BASE_URL}/PublicHolidays/{year}/{SRI_LANKA_COUNTRY_CODE}",
        headers={"Accept": "application/json", "User-Agent": "RouteMVP/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    if not response.text.strip():
        return []

    try:
        data = response.json()
    except json.JSONDecodeError:
        return []

    return data if isinstance(data, list) else []


def _level_from_score(score: int) -> str:
    if score >= 35:
        return "high"
    if score >= 18:
        return "medium"
    return "low"


def _window_level(score: int) -> str:
    if score >= 46:
        return "worst"
    if score >= 32:
        return "bad"
    if score >= 18:
        return "good"
    return "best"


def _pressure_text(level: str) -> str:
    return level.replace("_", " ").title()


def _holiday_pressure_for_date(
    *,
    iso_date: str,
    weekend_dates: set[str],
    holiday_matches: dict[str, dict[str, Any]],
) -> tuple[int, list[str]]:
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
        reasons.append("weekend leisure demand can increase attraction and road pressure")
    return score, reasons


def _summarize_weather_pressure(route: dict[str, Any]) -> dict[str, Any]:
    segments = route.get("segments") or []
    flagged_days = []
    score = 0

    for segment in segments:
        risk = segment.get("weather", {}).get("risk", {})
        risk_score = risk.get("score")
        if risk_score is None:
            continue

        if risk_score >= 60:
            severity = "high"
            score += 12
        elif risk_score >= 30:
            severity = "medium"
            score += 6
        else:
            continue

        forecast = segment.get("weather", {}).get("forecast", {})
        day_index = max(int(segment.get("day", 1)) - 1, 0)
        flagged_days.append(
            {
                "date": (forecast.get("dates") or [None] * (day_index + 1))[day_index],
                "day": segment.get("day"),
                "severity": severity,
                "reasons": risk.get("reasons", []),
            }
        )

    if segments and flagged_days:
        level = _level_from_score(score)
        summary = f"{len(flagged_days)} trip day(s) show elevated weather disruption risk."
    elif segments:
        level = "low"
        summary = "No major weather disruption is currently flagged across the trip."
    else:
        level = "unknown"
        summary = "Weather forecast data is unavailable for this route."

    return {
        "level": level,
        "score": score,
        "summary": summary,
        "flagged_days": flagged_days[:5],
    }


def _summarize_road_pressure(route: dict[str, Any]) -> dict[str, Any]:
    road_alerts = route.get("road_alerts") or {}
    if not road_alerts:
        return {
            "level": "unknown",
            "score": 0,
            "summary": "Road incident data is unavailable.",
            "critical_count": 0,
            "incident_count": 0,
        }

    risk_level = road_alerts.get("risk_level", "unknown")
    critical_count = int(road_alerts.get("critical_count", 0) or 0)
    incident_count = int(road_alerts.get("total_deduplicated", 0) or 0)

    score = 0
    if risk_level == "high":
        score += 22
    elif risk_level == "medium":
        score += 12
    elif risk_level == "low":
        score += 4

    score += min(critical_count * 4, 16)

    summary = (
        f"{critical_count} critical road alert(s) and {incident_count} notable "
        "route-side incident(s) were detected."
    )

    return {
        "level": risk_level,
        "score": score,
        "summary": summary,
        "critical_count": critical_count,
        "incident_count": incident_count,
    }


def _summarize_traffic_pressure(route: dict[str, Any]) -> dict[str, Any]:
    traffic_data = route.get("traffic_data") or {}
    if not traffic_data or traffic_data.get("status") != "ok":
        return {
            "level": "unknown",
            "score": 0,
            "summary": "Live route traffic data is unavailable.",
            "delay_minutes": None,
            "slow_ratio": None,
            "jam_ratio": None,
        }

    return {
        "level": traffic_data.get("risk_level", "unknown"),
        "score": int(traffic_data.get("congestion_score", 0) or 0),
        "summary": traffic_data.get("summary") or "Live traffic looks manageable.",
        "delay_minutes": traffic_data.get("delay_minutes"),
        "slow_ratio": traffic_data.get("slow_ratio"),
        "jam_ratio": traffic_data.get("jam_ratio"),
    }


def _segment_candidate_places(segment: dict[str, Any]) -> list[dict[str, Any]]:
    selected = segment.get("gemini_selected_attractions") or []
    if selected:
        return selected
    top = segment.get("top_attractions") or []
    return top[:5]


def _segment_all_places(segment: dict[str, Any]) -> list[dict[str, Any]]:
    top = segment.get("top_attractions") or []
    return top[:8]


def _segment_districts(segment: dict[str, Any]) -> list[str]:
    districts = []
    for place in _segment_all_places(segment):
        district = place.get("district")
        if district and district not in districts:
            districts.append(district)
    return districts


def _infer_corridor_label(districts: list[str]) -> str:
    district_set = set(districts)
    for label, members in CORRIDOR_RULES:
        if district_set & members:
            return label
    if districts:
        return f"{districts[0]} Corridor"
    return "Unclassified Corridor"


def _segment_weather_modifier(segment: dict[str, Any]) -> tuple[int, list[str]]:
    risk = segment.get("weather", {}).get("risk", {})
    risk_score = int(risk.get("score") or 0)
    if risk_score >= 60:
        return 12, [*risk.get("reasons", [])[:2]]
    if risk_score >= 30:
        return 6, [*risk.get("reasons", [])[:2]]
    return 0, []


def _segment_route_friction_modifier(road_pressure: dict[str, Any], *, day_index: int) -> tuple[int, list[str]]:
    base = int(round((road_pressure.get("score", 0) or 0) / max(day_index + 1, 1)))
    modifier = min(max(base // 2, 0), 10)
    reasons = []
    if modifier:
        reasons.append("route-side incidents can amplify delays during this travel day")
    return modifier, reasons


def _segment_traffic_modifier(traffic_pressure: dict[str, Any], *, day_index: int) -> tuple[int, list[str]]:
    if traffic_pressure.get("level") == "unknown":
        return 0, []
    base = int(traffic_pressure.get("score", 0) or 0)
    modifier = min(max(base // 3, 0), 14) if day_index == 0 else min(max(base // (6 + day_index), 0), 4)
    reasons = []
    if modifier:
        reasons.append("live departure traffic can increase route friction")
    return modifier, reasons


def _build_zone_pressure(
    *,
    route: dict[str, Any],
    trip_dates: list[str],
    weekend_dates: set[str],
    holiday_matches: dict[str, dict[str, Any]],
    weather_pressure: dict[str, Any],
    road_pressure: dict[str, Any],
    traffic_pressure: dict[str, Any],
) -> dict[str, Any]:
    segments = route.get("segments") or []
    day_rows = []
    district_rollup: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"district": "", "scores": [], "days": [], "corridors": set(), "reasons": []}
    )
    corridor_rollup: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"corridor": "", "scores": [], "days": [], "districts": set(), "reasons": []}
    )

    for index, segment in enumerate(segments):
        day_index = max(int(segment.get("day", index + 1)) - 1, 0)
        iso_date = trip_dates[min(day_index, len(trip_dates) - 1)]
        holiday_score, holiday_reasons = _holiday_pressure_for_date(
            iso_date=iso_date,
            weekend_dates=weekend_dates,
            holiday_matches=holiday_matches,
        )
        weather_score, weather_reasons = _segment_weather_modifier(segment)
        road_score, road_reasons = _segment_route_friction_modifier(road_pressure, day_index=day_index)
        traffic_score, traffic_reasons = _segment_traffic_modifier(traffic_pressure, day_index=day_index)

        base_score = holiday_score + weather_score + road_score + traffic_score
        pressure_score = min(100, max(base_score, 0))
        pressure_level = _level_from_score(pressure_score)
        districts = _segment_districts(segment)
        corridor = _infer_corridor_label(districts)

        if pressure_level == "high":
            preferred_visit_window = "early_morning"
        elif weather_score >= 6:
            preferred_visit_window = "late_morning"
        else:
            preferred_visit_window = "mid_morning"

        day_reasons = [*holiday_reasons, *weather_reasons, *road_reasons, *traffic_reasons]
        if not day_reasons:
            day_reasons = ["conditions look manageable for this day segment"]

        day_row = {
            "day": segment.get("day", index + 1),
            "date": iso_date,
            "districts": districts,
            "corridor": corridor,
            "pressure_score": pressure_score,
            "pressure_level": pressure_level,
            "preferred_visit_window": preferred_visit_window,
            "reasons": day_reasons[:4],
            "components": {
                "holiday": holiday_score,
                "weather": weather_score,
                "road": road_score,
                "traffic": traffic_score,
            },
        }
        day_rows.append(day_row)

        for district in districts:
            bucket = district_rollup[district]
            bucket["district"] = district
            bucket["scores"].append(pressure_score)
            bucket["days"].append(day_row["day"])
            bucket["corridors"].add(corridor)
            bucket["reasons"].extend(day_reasons[:2])

        corridor_bucket = corridor_rollup[corridor]
        corridor_bucket["corridor"] = corridor
        corridor_bucket["scores"].append(pressure_score)
        corridor_bucket["days"].append(day_row["day"])
        corridor_bucket["districts"].update(districts)
        corridor_bucket["reasons"].extend(day_reasons[:2])

    districts = []
    for district, bucket in district_rollup.items():
        avg_score = round(sum(bucket["scores"]) / max(len(bucket["scores"]), 1))
        districts.append(
            {
                "district": district,
                "pressure_score": avg_score,
                "pressure_level": _level_from_score(avg_score),
                "days": sorted(set(bucket["days"])),
                "corridors": sorted(bucket["corridors"]),
                "reasons": list(dict.fromkeys(bucket["reasons"]))[:3],
            }
        )

    corridors = []
    for corridor, bucket in corridor_rollup.items():
        avg_score = round(sum(bucket["scores"]) / max(len(bucket["scores"]), 1))
        corridors.append(
            {
                "corridor": corridor,
                "pressure_score": avg_score,
                "pressure_level": _level_from_score(avg_score),
                "days": sorted(set(bucket["days"])),
                "districts": sorted(bucket["districts"]),
                "reasons": list(dict.fromkeys(bucket["reasons"]))[:3],
            }
        )

    return {
        "days": day_rows,
        "districts": sorted(districts, key=lambda item: item["pressure_score"], reverse=True),
        "corridors": sorted(corridors, key=lambda item: item["pressure_score"], reverse=True),
    }


def _attraction_weather_exposure(place: dict[str, Any]) -> int:
    categories = {str(item).lower() for item in place.get("types", [])}
    tags = {str(item).lower() for item in place.get("tags", [])}
    if categories & OUTDOOR_CATEGORIES or tags & OUTDOOR_TAGS:
        return 10
    if categories & {"museum", "historic", "cultural", "religious"}:
        return 3
    return 6


def _attraction_iconic_modifier(place: dict[str, Any]) -> int:
    tags = {str(item).lower() for item in place.get("tags", [])}
    tier = place.get("tier")
    score = 0
    if tags & CROWD_SENSITIVE_TAGS:
        score += 8
    if tier == "tier_1":
        score += 6
    elif tier == "tier_2":
        score += 3
    return score


def _build_attraction_pressure(
    *,
    route: dict[str, Any],
    zone_pressure: dict[str, Any],
    weekend_dates: set[str],
    holiday_matches: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    day_lookup = {row["day"]: row for row in zone_pressure.get("days", [])}
    advisories = []

    for segment in route.get("segments") or []:
        day = segment.get("day")
        day_pressure = day_lookup.get(day, {})
        iso_date = day_pressure.get("date")
        is_weekend = iso_date in weekend_dates if iso_date else False
        is_holiday = iso_date in holiday_matches if iso_date else False
        weather_risk = segment.get("weather", {}).get("risk", {})
        weather_score = int(weather_risk.get("score") or 0)
        candidate_places = _segment_all_places(segment)
        selected_ids = {
            place.get("place_id")
            for place in _segment_candidate_places(segment)
            if place.get("place_id")
        }

        for place in candidate_places:
            pressure_score = int(day_pressure.get("pressure_score", 0))
            reasons = []

            if is_weekend:
                pressure_score += 4
                reasons.append("weekend travel demand can make this attraction busier")
            if is_holiday:
                pressure_score += 8
                reasons.append("public holiday timing can increase visitor density")

            iconic_bonus = _attraction_iconic_modifier(place)
            if iconic_bonus:
                pressure_score += iconic_bonus
                reasons.append("this is a high-visibility attraction that tends to pull more visitors")

            weather_exposure = _attraction_weather_exposure(place)
            if weather_score >= 60:
                pressure_score += weather_exposure
                reasons.append("forecast disruption can affect the comfort of this stop")
            elif weather_score >= 30:
                pressure_score += max(weather_exposure // 2, 1)
                reasons.append("weather conditions may slightly reduce comfort at this stop")

            distance_penalty = int(min(float(place.get("distance_from_route_m") or 0) / 4000, 6))
            pressure_score += distance_penalty
            if distance_penalty >= 3:
                reasons.append("it sits a bit farther from the main route corridor")

            pressure_score = min(100, pressure_score)
            level = _level_from_score(pressure_score)
            advisories.append(
                {
                    "place_id": place.get("place_id"),
                    "day": day,
                    "date": iso_date,
                    "name": place.get("display_name"),
                    "district": place.get("district"),
                    "pressure_score": pressure_score,
                    "pressure_level": level,
                    "preferred_visit_window": day_pressure.get("preferred_visit_window", "mid_morning"),
                    "is_selected": place.get("place_id") in selected_ids,
                    "reasons": reasons[:4] or ["route conditions around this attraction look manageable"],
                }
            )

    return advisories


def _build_forecast_windows(
    zone_pressure: dict[str, Any],
) -> list[dict[str, Any]]:
    windows = []
    adjustments = [
        ("early_morning", -8),
        ("late_morning", -4),
        ("afternoon", 4),
        ("evening", 8),
    ]
    for day in zone_pressure.get("days", []):
        day_windows = []
        for label, adjustment in adjustments:
            score = max(0, min(100, int(day.get("pressure_score", 0)) + adjustment))
            day_windows.append(
                {
                    "label": label,
                    "score": score,
                    "level": _window_level(score),
                }
            )
        day_windows.sort(key=lambda item: item["score"])
        windows.append(
            {
                "day": day["day"],
                "date": day["date"],
                "corridor": day["corridor"],
                "best_window": day_windows[0],
                "avoid_window": day_windows[-1],
                "windows": day_windows,
            }
        )
    return windows


def _build_redistribution_suggestions(
    *,
    route: dict[str, Any],
    zone_pressure: dict[str, Any],
    attraction_pressure: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_day_pressure = {item["day"]: item for item in zone_pressure.get("days", [])}
    by_day_attractions: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in attraction_pressure:
        by_day_attractions[int(item["day"])].append(item)

    suggestions = []
    for segment in route.get("segments") or []:
        day = int(segment.get("day", 0) or 0)
        day_pressure = by_day_pressure.get(day)
        if not day_pressure:
            continue

        if day_pressure["pressure_level"] in {"medium", "high"}:
            suggestions.append(
                {
                    "type": "time_shift",
                    "day": day,
                    "date": day_pressure["date"],
                    "priority": "high" if day_pressure["pressure_level"] == "high" else "medium",
                    "title": f"Shift Day {day} sightseeing earlier",
                    "message": (
                        f"Expected pressure is {_pressure_text(day_pressure['pressure_level']).lower()} in the "
                        f"{day_pressure['corridor']}. Start around {day_pressure['preferred_visit_window'].replace('_', ' ')} "
                        "to reduce route friction and attraction crowding."
                    ),
                }
            )

        advisories = sorted(by_day_attractions.get(day, []), key=lambda item: item["pressure_score"])
        selected = [item for item in advisories if item.get("is_selected")]
        candidate_alternatives = [item for item in advisories if not item.get("is_selected")]
        if selected:
            busiest_selected = max(selected, key=lambda item: item["pressure_score"])
            lower_alt = next(
                (
                    item
                    for item in candidate_alternatives
                    if item["pressure_score"] + 8 < busiest_selected["pressure_score"]
                ),
                None,
            )
            if lower_alt and busiest_selected["pressure_level"] in {"medium", "high"}:
                suggestions.append(
                    {
                        "type": "attraction_alternative",
                        "day": day,
                        "date": busiest_selected["date"],
                        "priority": "medium",
                        "title": f"Use a lower-pressure alternative on Day {day}",
                        "message": (
                            f"If {busiest_selected['name']} feels too busy, consider {lower_alt['name']} in "
                            f"{lower_alt.get('district') or 'the same corridor'} instead."
                        ),
                        "from_place_id": busiest_selected["place_id"],
                        "to_place_id": lower_alt["place_id"],
                    }
                )

        if segment.get("is_overnight_stop"):
            top_lodging = segment.get("top_lodging") or []
            recommended = segment.get("recommended_lodging") or {}
            alternative_lodging = next(
                (
                    item for item in top_lodging
                    if item.get("place_id") and item.get("place_id") != recommended.get("place_id")
                ),
                None,
            )
            if alternative_lodging and day_pressure["pressure_level"] == "high":
                suggestions.append(
                    {
                        "type": "overnight_alternative",
                        "day": day,
                        "date": day_pressure["date"],
                        "priority": "medium",
                        "title": f"Keep an overnight backup for Day {day}",
                        "message": (
                            f"If access around the planned overnight area becomes slow, keep {alternative_lodging.get('display_name')} "
                            "as a backup stay option."
                        ),
                        "stay_place_id": alternative_lodging.get("place_id"),
                    }
                )

    return suggestions[:10]


def get_crowd_signals_for_route(
    *,
    route: dict[str, Any],
    start_date: str,
    trip_days: int,
) -> dict[str, Any]:
    trip_dates = build_trip_dates(start_date, trip_days)
    years = sorted({date.fromisoformat(day).year for day in trip_dates})

    holidays: list[dict[str, Any]] = []
    fetch_warnings = []
    for year in years:
        try:
            holidays.extend(_get_public_holidays(year))
        except requests.RequestException as exc:
            fetch_warnings.append(f"Holiday API request failed for {year}: {exc}")

    holidays_by_date = {holiday["date"]: holiday for holiday in holidays}
    holiday_matches = []
    weekend_dates = []

    for iso_date in trip_dates:
        day_obj = date.fromisoformat(iso_date)
        if day_obj.weekday() >= 5:
            weekend_dates.append(iso_date)
        if iso_date in holidays_by_date:
            holiday = holidays_by_date[iso_date]
            holiday_matches.append(
                {
                    "date": iso_date,
                    "name": holiday.get("name"),
                    "local_name": holiday.get("localName"),
                    "types": holiday.get("types", []),
                }
            )

    holiday_score = 0
    reasons = []
    if holiday_matches:
        holiday_score += 22 + max(0, len(holiday_matches) - 1) * 6
        reasons.append(f"{len(holiday_matches)} public holiday date(s) fall within the trip.")
    if weekend_dates:
        holiday_score += 5 if len(weekend_dates) == 1 else 10
        reasons.append(f"{len(weekend_dates)} trip date(s) fall on a weekend.")
    reasons.extend(fetch_warnings)

    holiday_level = "unknown" if fetch_warnings else _level_from_score(holiday_score)
    weather_pressure = _summarize_weather_pressure(route)
    road_pressure = _summarize_road_pressure(route)
    traffic_pressure = _summarize_traffic_pressure(route)

    if weather_pressure["flagged_days"]:
        reasons.append(weather_pressure["summary"])
    if road_pressure["incident_count"]:
        reasons.append(road_pressure["summary"])
    if traffic_pressure["level"] != "unknown":
        reasons.append(traffic_pressure["summary"])

    signal_score = holiday_score + weather_pressure["score"] + road_pressure["score"] + traffic_pressure["score"]
    risk_level = _level_from_score(signal_score)
    if fetch_warnings and not holiday_matches and not weekend_dates:
        risk_level = "unknown"

    holiday_lookup = {item["date"]: item for item in holiday_matches if item.get("date")}
    zone_pressure = _build_zone_pressure(
        route=route,
        trip_dates=trip_dates,
        weekend_dates=set(weekend_dates),
        holiday_matches=holiday_lookup,
        weather_pressure=weather_pressure,
        road_pressure=road_pressure,
        traffic_pressure=traffic_pressure,
    )
    attraction_pressure = _build_attraction_pressure(
        route=route,
        zone_pressure=zone_pressure,
        weekend_dates=set(weekend_dates),
        holiday_matches=holiday_lookup,
    )
    forecast_windows = _build_forecast_windows(zone_pressure)
    redistribution_suggestions = _build_redistribution_suggestions(
        route=route,
        zone_pressure=zone_pressure,
        attraction_pressure=attraction_pressure,
    )

    recommendations = []
    if holiday_matches:
        recommendations.append(
            "Prioritize early departures and pre-book popular attractions because holiday demand is elevated."
        )
    if road_pressure["critical_count"] > 0:
        recommendations.append(
            "Keep route sequencing flexible and re-check RoadLK updates before long transfers."
        )
    if traffic_pressure["level"] in {"medium", "high"}:
        recommendations.append(
            "Live route traffic is elevated, so leave extra buffer time for the first major travel window."
        )
    if weather_pressure["flagged_days"]:
        recommendations.append(
            "Use indoor or short-stay activities on the highest rain-risk day and leave buffer time for travel."
        )
    if redistribution_suggestions:
        recommendations.append(
            "Use the redistribution suggestions to shift timing or swap high-pressure stops before the itinerary is finalized."
        )
    if not recommendations:
        recommendations.append(
            "Current signals look manageable, so the trip can prioritize comfort, pacing, and attraction fit."
        )

    helper_summary = (
        f"Trip pressure is {risk_level}. "
        f"Holiday demand is {holiday_level}, weather disruption is {weather_pressure['level']}, "
        f"road disruption is {road_pressure['level']}, and live traffic is {traffic_pressure['level']}."
    )

    return {
        "trip_dates": trip_dates,
        "holiday_matches": holiday_matches,
        "weekend_dates": weekend_dates,
        "risk_level": risk_level,
        "signal_score": signal_score,
        "holiday_api_status": "degraded" if fetch_warnings else "ok",
        "helper_summary": helper_summary,
        "reasons": reasons,
        "recommendations": recommendations,
        "zone_pressure": zone_pressure,
        "attraction_pressure": attraction_pressure,
        "forecast_windows": forecast_windows,
        "redistribution_suggestions": redistribution_suggestions,
        "components": {
            "holiday_pressure": {
                "level": holiday_level,
                "score": holiday_score,
                "summary": (
                    "Holiday and weekend timing suggest elevated visitor demand."
                    if holiday_score
                    else "No strong holiday-driven demand pressure is currently detected."
                ),
            },
            "weather_pressure": weather_pressure,
            "road_pressure": road_pressure,
            "traffic_pressure": traffic_pressure,
        },
    }
