from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from google_routes.client import compute_routes

SRI_LANKA_TZ = timezone(timedelta(hours=5, minutes=30))


def _parse_duration_seconds(value: str | None) -> int | None:
    if not value or not isinstance(value, str) or not value.endswith("s"):
        return None
    try:
        return int(float(value[:-1]))
    except ValueError:
        return None


def _build_departure_time(start_date: str, departure_time: str | None) -> str:
    safe_time = departure_time or "08:00"
    dt = datetime.fromisoformat(f"{start_date}T{safe_time}:00")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SRI_LANKA_TZ)
    return dt.isoformat()


def _speed_interval_ratio(interval: dict[str, Any]) -> int:
    start = int(interval.get("startPolylinePointIndex", 0) or 0)
    end = int(interval.get("endPolylinePointIndex", start + 1) or (start + 1))
    return max(end - start, 1)


def summarize_route_traffic(route_payload: dict[str, Any]) -> dict[str, Any]:
    route = ((route_payload.get("routes") or [{}])[0]) if route_payload else {}
    duration_seconds = _parse_duration_seconds(route.get("duration"))
    static_duration_seconds = _parse_duration_seconds(route.get("staticDuration"))
    intervals = ((route.get("travelAdvisory") or {}).get("speedReadingIntervals")) or []

    weights = {"NORMAL": 0, "SLOW": 0, "TRAFFIC_JAM": 0, "SPEED_UNSPECIFIED": 0}
    for interval in intervals:
        speed = str(interval.get("speed") or "SPEED_UNSPECIFIED").upper()
        weights[speed] = weights.get(speed, 0) + _speed_interval_ratio(interval)

    total_weight = max(sum(weights.values()), 1)
    slow_ratio = round(((weights.get("SLOW", 0) + weights.get("TRAFFIC_JAM", 0)) / total_weight) * 100, 1)
    jam_ratio = round((weights.get("TRAFFIC_JAM", 0) / total_weight) * 100, 1)
    normal_ratio = round((weights.get("NORMAL", 0) / total_weight) * 100, 1)

    delay_seconds = None
    delay_minutes = None
    if duration_seconds is not None and static_duration_seconds is not None:
        delay_seconds = max(duration_seconds - static_duration_seconds, 0)
        delay_minutes = round(delay_seconds / 60, 1)

    congestion_score = 0
    if delay_seconds is not None:
        congestion_score += min(int(delay_seconds / 60), 18)
    congestion_score += int(round(slow_ratio * 0.35))
    congestion_score += int(round(jam_ratio * 0.55))
    congestion_score = min(congestion_score, 100)

    if congestion_score >= 40:
        level = "high"
    elif congestion_score >= 18:
        level = "medium"
    else:
        level = "low"

    summary_bits = []
    if delay_minutes is not None:
        if delay_minutes >= 15:
            summary_bits.append(f"live traffic adds about {delay_minutes:.0f} minutes")
        elif delay_minutes > 0:
            summary_bits.append(f"live traffic adds about {delay_minutes:.0f} minutes")
        else:
            summary_bits.append("traffic delay is currently light")
    if jam_ratio >= 10:
        summary_bits.append(f"{jam_ratio:.0f}% of sampled route segments look jammed")
    elif slow_ratio >= 20:
        summary_bits.append(f"{slow_ratio:.0f}% of sampled route segments are slower than normal")
    else:
        summary_bits.append("most sampled route segments look close to normal flow")

    return {
        "status": "ok",
        "live_duration_seconds": duration_seconds,
        "static_duration_seconds": static_duration_seconds,
        "delay_seconds": delay_seconds,
        "delay_minutes": delay_minutes,
        "normal_ratio": normal_ratio,
        "slow_ratio": slow_ratio,
        "jam_ratio": jam_ratio,
        "congestion_score": congestion_score,
        "risk_level": level,
        "speed_interval_count": len(intervals),
        "summary": ". ".join(summary_bits),
        "raw_route": route,
    }


def enrich_route_with_live_traffic(
    *,
    route: dict[str, Any],
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    start_date: str,
    departure_time: str | None,
) -> dict[str, Any]:
    response_payload = compute_routes(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        destination_lat=destination_lat,
        destination_lng=destination_lng,
        travel_mode="DRIVE",
        routing_preference="TRAFFIC_AWARE",
        compute_alternative_routes=False,
        departure_time=_build_departure_time(start_date, departure_time),
        extra_computations=["TRAFFIC_ON_POLYLINE"],
        field_mask="routes.duration,routes.staticDuration,routes.travelAdvisory.speedReadingIntervals,routes.polyline.encodedPolyline",
        timeout=30,
    )
    traffic_data = summarize_route_traffic(response_payload)
    return {**route, "traffic_data": traffic_data}
