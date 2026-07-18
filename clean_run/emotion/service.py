from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any


NEGATIVE_EMOTIONS = {"anger", "sad"}
POSITIVE_EMOTIONS = {"happy", "surprise"}
NEUTRAL_EMOTIONS = {"neutral"}
DEFAULT_CHECKIN_RADIUS_METERS = 200
CHECKIN_TYPES = {"attraction", "start_of_day"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _level_from_score(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _extract_lat_lng(item: dict[str, Any]) -> tuple[float, float] | None:
    location = item.get("location") or item.get("geo") or {}
    lat = (
        item.get("lat")
        or item.get("latitude")
        or location.get("lat")
        or location.get("latitude")
    )
    lng = (
        item.get("lng")
        or item.get("lon")
        or item.get("longitude")
        or location.get("lng")
        or location.get("lon")
        or location.get("longitude")
    )
    lat_value = _safe_float(lat)
    lng_value = _safe_float(lng)
    if lat_value is None or lng_value is None:
        return None
    return lat_value, lng_value


def _haversine_meters(
    lat_a: float,
    lng_a: float,
    lat_b: float,
    lng_b: float,
) -> float:
    earth_radius_m = 6_371_000
    delta_lat = math.radians(lat_b - lat_a)
    delta_lng = math.radians(lng_b - lng_a)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(math.radians(lat_a))
        * math.cos(math.radians(lat_b))
        * math.sin(delta_lng / 2) ** 2
    )
    return 2 * earth_radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _attraction_name(attraction: dict[str, Any]) -> str:
    return str(
        attraction.get("display_name")
        or attraction.get("name")
        or attraction.get("title")
        or attraction.get("formattedAddress")
        or ""
    ).strip()


def _attraction_id(attraction: dict[str, Any]) -> str | None:
    value = (
        attraction.get("attraction_id")
        or attraction.get("place_id")
        or attraction.get("id")
        or attraction.get("google_place_id")
    )
    return str(value).strip() if value else None


def _segment_attractions(segment: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        segment.get("gemini_selected_attractions")
        or segment.get("selected_attractions")
        or segment.get("top_attractions")
        or []
    )


def _iter_plan_attractions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    recommended_route = plan.get("recommended_route") or {}
    segments = recommended_route.get("segments") or []
    targets: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()

    for segment in segments:
        day = segment.get("day")
        day_label = segment.get("day_label") or f"Day {day}"
        for index, attraction in enumerate(_segment_attractions(segment), start=1):
            if not isinstance(attraction, dict):
                continue
            name = _attraction_name(attraction)
            coords = _extract_lat_lng(attraction)
            attraction_id = _attraction_id(attraction) or (
                f"day-{day}-attraction-{index}" if day is not None else None
            )
            key = (day, attraction_id, name)
            if key in seen:
                continue
            seen.add(key)
            targets.append(
                {
                    "attraction_id": attraction_id,
                    "attraction_name": name,
                    "day": day,
                    "day_label": day_label,
                    "order": index,
                    "district": attraction.get("district"),
                    "category": attraction.get("category") or attraction.get("primary_type"),
                    "latitude": coords[0] if coords else None,
                    "longitude": coords[1] if coords else None,
                    "checkin_radius_meters": int(
                        attraction.get("checkin_radius_meters")
                        or attraction.get("radius_meters")
                        or DEFAULT_CHECKIN_RADIUS_METERS
                    ),
                    "source": "recommended_route.selected_attractions",
                }
            )
    return targets


def build_emotion_checkin_targets(session_document: dict[str, Any]) -> dict[str, Any]:
    """Return planned attraction geofence targets for the mobile app."""

    plan = session_document.get("plan") or {}
    targets = _iter_plan_attractions(plan)
    emotion_checkins = list(session_document.get("emotion_checkins") or [])
    return {
        "session_id": session_document.get("session_id"),
        "target_count": len(targets),
        "targets": targets,
        "emotion_checkins": emotion_checkins,
        "emotion_summary": session_document.get("emotion_summary") or {},
        "mobile_flow": {
            "geofence_on_device": True,
            "raw_image_upload_required": False,
            "local_tflite_inference_required": True,
            "recommended_crop_scale": 1.0,
            "optional_stability_crop_scales": [0.95, 1.0, 1.05],
        },
    }


def _find_target_for_checkin(
    *,
    checkin: dict[str, Any],
    session_document: dict[str, Any],
) -> dict[str, Any] | None:
    targets = _iter_plan_attractions(session_document.get("plan") or {})
    if not targets:
        return None

    checkin_id = _normalize_text(checkin.get("attraction_id"))
    checkin_name = _normalize_text(checkin.get("attraction_name"))
    if checkin_id:
        for target in targets:
            if _normalize_text(target.get("attraction_id")) == checkin_id:
                return target
    if checkin_name:
        for target in targets:
            target_name = _normalize_text(target.get("attraction_name"))
            if target_name and (checkin_name in target_name or target_name in checkin_name):
                return target

    user_location = checkin.get("user_location") or {}
    user_lat = _safe_float(user_location.get("latitude") or user_location.get("lat"))
    user_lng = _safe_float(user_location.get("longitude") or user_location.get("lng"))
    if user_lat is None or user_lng is None:
        return None

    candidates = []
    for target in targets:
        target_lat = _safe_float(target.get("latitude"))
        target_lng = _safe_float(target.get("longitude"))
        if target_lat is None or target_lng is None:
            continue
        candidates.append(
            (
                _haversine_meters(user_lat, user_lng, target_lat, target_lng),
                target,
            )
        )
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def attach_location_context(
    *,
    checkin: dict[str, Any],
    session_document: dict[str, Any],
) -> dict[str, Any]:
    """Attach planned-attraction and distance context to a sanitized check-in."""

    enriched = dict(checkin)
    target = _find_target_for_checkin(checkin=checkin, session_document=session_document)
    user_location = checkin.get("user_location") or {}
    user_lat = _safe_float(user_location.get("latitude") or user_location.get("lat"))
    user_lng = _safe_float(user_location.get("longitude") or user_location.get("lng"))

    location_context: dict[str, Any] = {
        "matched_planned_attraction": bool(target),
        "user_location_provided": user_lat is not None and user_lng is not None,
        "distance_to_attraction_meters": None,
        "within_checkin_radius": None,
        "checkin_radius_meters": None,
    }

    if checkin.get("checkin_type") == "start_of_day":
        location_context["matched_planned_attraction"] = False
        location_context["mode"] = "start_of_day"
        enriched["location_context"] = location_context
        return enriched

    if target:
        enriched["attraction_id"] = enriched.get("attraction_id") or target.get("attraction_id")
        enriched["attraction_name"] = enriched.get("attraction_name") or target.get("attraction_name")
        enriched["day"] = target.get("day")
        enriched["day_label"] = target.get("day_label")
        enriched["planned_attraction"] = {
            "attraction_id": target.get("attraction_id"),
            "attraction_name": target.get("attraction_name"),
            "day": target.get("day"),
            "day_label": target.get("day_label"),
            "order": target.get("order"),
            "latitude": target.get("latitude"),
            "longitude": target.get("longitude"),
            "district": target.get("district"),
        }

        target_lat = _safe_float(target.get("latitude"))
        target_lng = _safe_float(target.get("longitude"))
        radius = int(target.get("checkin_radius_meters") or DEFAULT_CHECKIN_RADIUS_METERS)
        location_context["checkin_radius_meters"] = radius
        if user_lat is not None and user_lng is not None and target_lat is not None and target_lng is not None:
            distance = round(_haversine_meters(user_lat, user_lng, target_lat, target_lng), 1)
            location_context["distance_to_attraction_meters"] = distance
            location_context["within_checkin_radius"] = distance <= radius

    enriched["location_context"] = location_context
    return enriched


def _emotion_stress_score(label: str, confidence: float) -> int:
    normalized = label.lower().strip()
    confidence_score = max(0.0, min(float(confidence), 1.0))
    if normalized in NEGATIVE_EMOTIONS:
        return int(round(45 + (35 * confidence_score)))
    if normalized in NEUTRAL_EMOTIONS:
        return int(round(25 + (20 * confidence_score)))
    if normalized in POSITIVE_EMOTIONS:
        return max(0, int(round(20 - (10 * confidence_score))))
    return 35


def _extract_next_segment(plan: dict[str, Any], attraction_name: str | None) -> dict[str, Any] | None:
    recommended_route = plan.get("recommended_route") or {}
    segments = recommended_route.get("segments") or []
    if not segments:
        return None

    if attraction_name:
        normalized_target = attraction_name.lower().strip()
        for index, segment in enumerate(segments):
            attractions = (
                segment.get("gemini_selected_attractions")
                or segment.get("selected_attractions")
                or segment.get("top_attractions")
                or []
            )
            for attraction in attractions:
                name = (
                    attraction.get("display_name")
                    or attraction.get("name")
                    or attraction.get("title")
                    or ""
                )
                if normalized_target and normalized_target in name.lower():
                    if index + 1 < len(segments):
                        return segments[index + 1]
                    return segment

    return segments[0]


def _extract_day_segment(plan: dict[str, Any], day: Any) -> dict[str, Any] | None:
    recommended_route = plan.get("recommended_route") or {}
    segments = recommended_route.get("segments") or []
    if not segments:
        return None

    try:
        day_number = int(day)
    except (TypeError, ValueError):
        day_number = None

    if day_number is not None:
        for segment in segments:
            try:
                if int(segment.get("day")) == day_number:
                    return segment
            except (TypeError, ValueError):
                continue

    return segments[0]


def _crowd_score(plan: dict[str, Any], next_segment: dict[str, Any] | None) -> tuple[int, str | None]:
    segment_signals = (next_segment or {}).get("crowd_signals") or {}
    plan_signals = plan.get("crowd_signals") or {}
    signal_score = segment_signals.get("signal_score") or plan_signals.get("signal_score")
    risk_level = segment_signals.get("risk_level") or plan_signals.get("risk_level")

    if isinstance(signal_score, (int, float)):
        return int(max(0, min(float(signal_score), 100))), risk_level
    if risk_level == "high":
        return 65, risk_level
    if risk_level == "medium":
        return 45, risk_level
    if risk_level == "low":
        return 20, risk_level
    return 30, risk_level


def _weather_score(next_segment: dict[str, Any] | None) -> tuple[int, str | None]:
    weather = (next_segment or {}).get("weather") or {}
    risk = weather.get("risk") or weather
    risk_level = risk.get("risk_level") or risk.get("level")
    risk_score = risk.get("risk_score") or risk.get("score")
    if isinstance(risk_score, (int, float)):
        return int(max(0, min(float(risk_score), 100))), risk_level
    if risk_level == "high":
        return 65, risk_level
    if risk_level == "medium":
        return 40, risk_level
    if risk_level == "low":
        return 10, risk_level
    return 15, risk_level


def _fatigue_score(next_segment: dict[str, Any] | None) -> tuple[int, float | None]:
    duration_seconds = (next_segment or {}).get("segment_duration_seconds")
    if duration_seconds is None:
        return 20, None
    hours = float(duration_seconds) / 3600
    if hours >= 3:
        return 65, hours
    if hours >= 1.5:
        return 45, hours
    if hours >= 0.75:
        return 25, hours
    return 10, hours


def _road_score(plan: dict[str, Any]) -> tuple[int, str | None, str | None]:
    recommended_route = plan.get("recommended_route") or {}
    road_alerts = plan.get("road_alerts") or recommended_route.get("road_alerts") or {}
    risk_level = road_alerts.get("risk_level")
    critical_count = int(road_alerts.get("critical_count", 0) or 0)
    incident_count = int(
        road_alerts.get("total_deduplicated")
        or road_alerts.get("total_near_route")
        or len(road_alerts.get("incidents") or [])
        or 0
    )

    if critical_count > 0:
        return 75, risk_level or "high", road_alerts.get("summary")
    if risk_level == "high":
        return 65, risk_level, road_alerts.get("summary")
    if risk_level == "medium" or incident_count > 0:
        return 40, risk_level or "medium", road_alerts.get("summary")
    if risk_level == "low":
        return 10, risk_level, road_alerts.get("summary")
    return 15, risk_level, road_alerts.get("summary")


def _segment_attraction_names(segment: dict[str, Any] | None) -> list[str]:
    names = []
    for attraction in _segment_attractions(segment or {}):
        if not isinstance(attraction, dict):
            continue
        name = _attraction_name(attraction)
        if name:
            names.append(name)
    return names[:5]


def sanitize_emotion_checkin(checkin: dict[str, Any]) -> dict[str, Any]:
    """Keep only structured inference metadata. Raw images never belong here."""

    allowed_top_predictions = []
    for item in checkin.get("top_predictions") or []:
        if not isinstance(item, dict):
            continue
        class_name = str(item.get("class_name") or item.get("label") or "").strip().lower()
        probability = item.get("probability")
        if not class_name:
            continue
        try:
            probability_value = float(probability)
        except (TypeError, ValueError):
            continue
        allowed_top_predictions.append(
            {
                "class_name": class_name,
                "probability": max(0.0, min(probability_value, 1.0)),
            }
        )

    emotion_label = str(checkin.get("emotion_label") or checkin.get("predicted_class") or "").strip().lower()
    confidence = float(checkin.get("emotion_confidence") or checkin.get("confidence") or 0)
    checkin_type = _normalize_text(checkin.get("checkin_type") or "attraction")
    if checkin_type not in CHECKIN_TYPES:
        checkin_type = "attraction"

    try:
        day = int(checkin.get("day")) if checkin.get("day") is not None else None
    except (TypeError, ValueError):
        day = None

    user_location = checkin.get("user_location") or {}
    user_lat = _safe_float(user_location.get("latitude") or user_location.get("lat"))
    user_lng = _safe_float(user_location.get("longitude") or user_location.get("lng"))

    sanitized = {
        "checkin_id": str(checkin.get("checkin_id") or ""),
        "attraction_id": checkin.get("attraction_id"),
        "attraction_name": checkin.get("attraction_name"),
        "checkin_type": checkin_type,
        "day": day,
        "timestamp": checkin.get("timestamp") or _now_iso(),
        "emotion_label": emotion_label,
        "emotion_confidence": max(0.0, min(confidence, 1.0)),
        "top_predictions": allowed_top_predictions[:5],
        "model_version": checkin.get("model_version") or "rafdb5_local_tflite",
        "local_inference": bool(checkin.get("local_inference", True)),
        "raw_image_stored": False,
        "hobbies": [
            str(item).strip()
            for item in (checkin.get("hobbies") or [])
            if str(item).strip()
        ],
    }
    if user_lat is not None and user_lng is not None:
        sanitized["user_location"] = {
            "latitude": user_lat,
            "longitude": user_lng,
            "accuracy_meters": _safe_float(user_location.get("accuracy_meters")),
        }
    return sanitized


def _emotion_value(label: str, confidence: float) -> float:
    confidence_score = max(0.0, min(float(confidence), 1.0))
    normalized = label.lower().strip()
    if normalized in POSITIVE_EMOTIONS:
        return confidence_score
    if normalized in NEGATIVE_EMOTIONS:
        return -confidence_score
    return 0.0


def build_emotion_summary(
    *,
    checkins: list[dict[str, Any]],
    latest_recommendation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    valid = [
        item
        for item in checkins
        if item.get("emotion_label") and item.get("emotion_label") != "uncertain"
    ]
    latest = checkins[-1] if checkins else None
    values = [
        _emotion_value(item.get("emotion_label", ""), float(item.get("emotion_confidence") or 0))
        for item in valid
    ]

    trend = "insufficient_data"
    recovery_status = "unknown"
    if len(values) >= 2:
        delta = values[-1] - values[0]
        if delta >= 0.35:
            trend = "improving"
        elif delta <= -0.35:
            trend = "declining"
        else:
            trend = "stable"

    negative_seen = any((item.get("emotion_label") or "").lower() in NEGATIVE_EMOTIONS for item in valid[:-1])
    latest_label = (latest or {}).get("emotion_label", "")
    if latest_label in POSITIVE_EMOTIONS and negative_seen:
        recovery_status = "recovered"
    elif latest_label in NEUTRAL_EMOTIONS and negative_seen:
        recovery_status = "partially_recovered"
    elif latest_label in NEGATIVE_EMOTIONS:
        recovery_status = "not_recovered"
    elif latest_label in POSITIVE_EMOTIONS:
        recovery_status = "positive"

    positive_contexts = [
        {
            "attraction_name": item.get("attraction_name"),
            "day": item.get("day"),
            "emotion": item.get("emotion_label"),
            "confidence": item.get("emotion_confidence"),
        }
        for item in valid
        if (item.get("emotion_label") or "").lower() in POSITIVE_EMOTIONS
    ][-3:]

    negative_contexts = [
        {
            "attraction_name": item.get("attraction_name"),
            "day": item.get("day"),
            "emotion": item.get("emotion_label"),
            "confidence": item.get("emotion_confidence"),
        }
        for item in valid
        if (item.get("emotion_label") or "").lower() in NEGATIVE_EMOTIONS
    ][-3:]

    return {
        "latest": latest or {},
        "count": len(checkins),
        "valid_signal_count": len(valid),
        "latest_recommendation": latest_recommendation or {},
        "trend": trend,
        "recovery_status": recovery_status,
        "average_mood_score": round(sum(values) / len(values), 3) if values else None,
        "positive_contexts": positive_contexts,
        "negative_contexts": negative_contexts,
        "raw_images_stored": False,
    }


def build_emotion_recommendation(
    *,
    checkin: dict[str, Any],
    session_document: dict[str, Any],
) -> dict[str, Any]:
    plan = session_document.get("plan") or {}
    latest_checkin = sanitize_emotion_checkin(checkin)
    next_segment = _extract_next_segment(plan, latest_checkin.get("attraction_name"))

    emotion_score = _emotion_stress_score(
        latest_checkin["emotion_label"],
        latest_checkin["emotion_confidence"],
    )
    crowd_score, crowd_level = _crowd_score(plan, next_segment)
    weather_score, weather_level = _weather_score(next_segment)
    fatigue_score, travel_hours = _fatigue_score(next_segment)

    combined_score = round(
        (emotion_score * 0.42)
        + (crowd_score * 0.24)
        + (weather_score * 0.18)
        + (fatigue_score * 0.16)
    )
    risk_level = _level_from_score(combined_score)

    reasons = [
        f"Latest check-in emotion is {latest_checkin['emotion_label']} with {latest_checkin['emotion_confidence']:.2f} confidence.",
        f"Crowd pressure contributes {crowd_score}/100"
        + (f" ({crowd_level})." if crowd_level else "."),
        f"Weather risk contributes {weather_score}/100"
        + (f" ({weather_level})." if weather_level else "."),
    ]
    if travel_hours is not None:
        reasons.append(f"Next travel segment is about {travel_hours:.1f} hours.")

    if risk_level == "high":
        prediction = "high chance of stress or fatigue before the next stop"
        recommendation = "Add a recovery break, food stop, or calmer nearby attraction before continuing."
    elif risk_level == "medium":
        prediction = "moderate chance of lower satisfaction at the next stop"
        recommendation = "Keep the next attraction, but use the best travel window and consider a short rest."
    else:
        prediction = "low emotional friction expected for the next stop"
        recommendation = "Continue as planned."

    return {
        "current_emotion": latest_checkin["emotion_label"],
        "confidence": latest_checkin["emotion_confidence"],
        "next_experience_prediction": prediction,
        "risk_level": risk_level,
        "score": combined_score,
        "components": {
            "emotion": emotion_score,
            "crowd": crowd_score,
            "weather": weather_score,
            "travel_fatigue": fatigue_score,
        },
        "explanation": reasons,
        "recommendation": recommendation,
        "next_segment": {
            "day": (next_segment or {}).get("day"),
            "day_label": (next_segment or {}).get("day_label"),
            "segment_duration_seconds": (next_segment or {}).get("segment_duration_seconds"),
            "segment_distance_km": (next_segment or {}).get("segment_distance_km"),
        },
        "privacy": {
            "local_inference": True,
            "raw_image_received_by_backend": False,
            "raw_image_stored": False,
        },
    }


def build_start_of_day_mood_recommendation(
    *,
    checkin: dict[str, Any],
    session_document: dict[str, Any],
) -> dict[str, Any]:
    """Build a day-ahead mood interpretation without mutating the trip plan."""

    plan = session_document.get("plan") or {}
    latest_checkin = sanitize_emotion_checkin({**checkin, "checkin_type": "start_of_day"})
    day_segment = _extract_day_segment(plan, latest_checkin.get("day"))

    emotion_score = _emotion_stress_score(
        latest_checkin["emotion_label"],
        latest_checkin["emotion_confidence"],
    )
    crowd_score, crowd_level = _crowd_score(plan, day_segment)
    weather_score, weather_level = _weather_score(day_segment)
    fatigue_score, travel_hours = _fatigue_score(day_segment)
    road_score, road_level, road_summary = _road_score(plan)

    combined_score = round(
        (emotion_score * 0.34)
        + (crowd_score * 0.22)
        + (weather_score * 0.18)
        + (fatigue_score * 0.16)
        + (road_score * 0.10)
    )
    risk_level = _level_from_score(combined_score)

    label = latest_checkin["emotion_label"]
    confidence = latest_checkin["emotion_confidence"]
    day_label = (day_segment or {}).get("day_label") or (
        f"Day {latest_checkin['day']}" if latest_checkin.get("day") else "Today"
    )
    attractions = _segment_attraction_names(day_segment)

    if label in NEGATIVE_EMOTIONS:
        mood_description = (
            f"The start-of-day photo suggests a heavier mood ({label}, {confidence:.2f} confidence), "
            "so the day should be paced more gently."
        )
    elif label in POSITIVE_EMOTIONS:
        mood_description = (
            f"The start-of-day photo suggests a positive mood ({label}, {confidence:.2f} confidence), "
            "so the planned day has good emotional momentum."
        )
    elif label in NEUTRAL_EMOTIONS:
        mood_description = (
            f"The start-of-day photo looks neutral ({confidence:.2f} confidence), "
            "so comfort depends more on crowd, weather, roads, and travel load."
        )
    else:
        mood_description = (
            "The model is uncertain about the start-of-day mood, so the advice leans on trip conditions."
        )

    # --- New recommendation building logic based on specific rules ---
    day_prediction_parts = []
    watch_out_for = []
    comfort_actions = []
    fallback_plan_parts = []
    timing_adj_parts = []
    recommendation = ""
    
    is_happy = label in POSITIVE_EMOTIONS
    is_neutral = label in NEUTRAL_EMOTIONS
    is_sad_anger = label in NEGATIVE_EMOTIONS
    is_surprise = label == "surprise"
    
    has_high_crowds = crowd_level in ["high", "severe"]
    has_high_weather = weather_level in ["high", "severe", "medium", "moderate"]
    has_high_roads = road_level in ["high", "severe", "medium", "moderate"]
    is_long_travel = travel_hours is not None and travel_hours >= 2.0
    
    # Base emotion logic
    if is_happy:
        summary = "You're starting with great energy!"
        day_prediction_parts.append("You’re starting with strong energy.")
        recommendation = "Visit the highest-priority attraction first while energy is high."
        if has_high_crowds or has_high_weather or has_high_roads:
            day_prediction_parts.append("Conditions require some caution later, so use the morning momentum.")
        else:
            day_prediction_parts.append("Conditions look good to carry this momentum through the day.")
        comfort_actions.append("Keep the afternoon lighter.")
    
    elif is_neutral:
        summary = "You're starting the day steady."
        day_prediction_parts.append("You have a steady start today.")
        recommendation = "Keep a balanced pace and avoid overloading the day."
        comfort_actions.append("Schedule one planned break to maintain energy.")
    
    elif is_sad_anger:
        summary = "A slower start today, which is totally okay."
        day_prediction_parts.append("A slower start today, which is totally fine.")
        recommendation = "Reduce intensity. Consider a slower first stop or swapping to an easier attraction."
        comfort_actions.append("Take a comfort break early on.")
        fallback_plan_parts.append("Drop the lowest-priority attraction if you feel tired.")
    
    elif is_surprise:
        summary = "An alert start to the day!"
        day_prediction_parts.append("You seem alert and ready for anything.")
        recommendation = "Keep the plan flexible to match your energy as the day goes on."
        comfort_actions.append("Keep your options open.")
    else:
        summary = "A solid start to the travel day."
        day_prediction_parts.append("The day ahead looks manageable.")
        recommendation = "Pace yourself based on how you feel after the first stop."
    
    # Context-specific logic
    if has_high_crowds:
        timing_adj_parts.append("Start earlier to beat the crowds, or shift the busiest attraction to the morning.")
        watch_out_for.append("Peak crowds building near main attractions.")
    else:
        if not timing_adj_parts:
            timing_adj_parts.append("Stick to your planned timing.")
            
    if has_high_weather:
        weather_text = "weather"
        watch_out_for.append(f"Sudden changes in {weather_text} conditions.")
        fallback_plan_parts.append("Keep a backup indoor activity ready or limit long outdoor exposure.")
        
    if has_high_roads:
        watch_out_for.append("Road friction points and possible delays.")
        timing_adj_parts.append("Add a 20-30 minute buffer to your travel time.")
        
    if is_long_travel:
        watch_out_for.append("Travel fatigue stacking up from driving.")
        comfort_actions.append("Take a stretch/snack break during the drive.")
        fallback_plan_parts.append("Trim optional stops if the drive feels too long.")
        
    if not fallback_plan_parts:
        if is_happy or is_neutral:
            fallback_plan_parts.append("No major fallbacks needed, but stay flexible.")
        else:
            fallback_plan_parts.append("Delay one minor stop if the schedule feels too rushed.")
    day_prediction = " ".join(day_prediction_parts)
    timing_adjustment = " ".join(timing_adj_parts)
    fallback_plan = " ".join(fallback_plan_parts)

    confidence_note = "High confidence read." if confidence > 0.7 else "Moderate confidence read."

    condition_bits = [
        f"crowd pressure is {crowd_level or 'unknown'}",
        f"weather risk is {weather_level or 'unknown'}",
        f"road risk is {road_level or 'unknown'}",
    ]
    if travel_hours is not None:
        condition_bits.append(f"travel load is about {travel_hours:.1f} hours")

    reasons = [
        mood_description,
        f"For {day_label}, " + ", ".join(condition_bits) + ".",
    ]
    if attractions:
        reasons.append("Planned stops considered: " + ", ".join(attractions) + ".")
    if road_summary:
        reasons.append(f"Road context: {road_summary}")

    return {
        "type": "start_of_day",
        "current_emotion": label,
        "confidence": confidence,
        "day": (day_segment or {}).get("day") or latest_checkin.get("day"),
        "day_label": day_label,
        "summary": summary,
        "day_ahead_prediction": day_prediction,
        "recommendation": recommendation,
        "timing_adjustment": timing_adjustment,
        "watch_out_for": watch_out_for,
        "comfort_actions": comfort_actions,
        "fallback_plan": fallback_plan,
        "confidence_note": confidence_note,
        "risk_level": risk_level,
        "score": combined_score,
        "components": {
            "emotion": emotion_score,
            "crowd": crowd_score,
            "weather": weather_score,
            "roads": road_score,
            "travel_fatigue": fatigue_score,
        },
        "explanation": reasons,
        "day_context": {
            "attractions": attractions,
            "crowd_level": crowd_level,
            "weather_level": weather_level,
            "road_level": road_level,
            "segment_duration_seconds": (day_segment or {}).get("segment_duration_seconds"),
            "segment_distance_km": (day_segment or {}).get("segment_distance_km"),
        },
        "privacy": {
            "local_inference": True,
            "raw_image_received_by_backend": False,
            "raw_image_stored": False,
            "identity_recognition": False,
        },
    }
