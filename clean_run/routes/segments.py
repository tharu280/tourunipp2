from __future__ import annotations

from typing import Any

from clean_run.routes.polyline import point_at_distance


def build_day_segments(
    *,
    decoded_points: list[dict[str, float]],
    cumulative_distances_m: list[float],
    total_route_distance_m: float,
    total_route_duration_seconds: int | None,
    trip_days: int,
) -> list[dict[str, Any]]:
    if trip_days < 1:
        raise ValueError("trip_days must be at least 1.")
    if not decoded_points:
        return []

    if total_route_distance_m <= 0:
        total_route_distance_m = cumulative_distances_m[-1] if cumulative_distances_m else 0.0

    segments = []

    for day_index in range(trip_days):
        start_ratio = day_index / trip_days
        end_ratio = (day_index + 1) / trip_days
        midpoint_ratio = (start_ratio + end_ratio) / 2

        start_distance = total_route_distance_m * start_ratio
        end_distance = total_route_distance_m * end_ratio
        midpoint_distance = total_route_distance_m * midpoint_ratio

        segment_distance = end_distance - start_distance
        segment_duration_seconds = None
        if total_route_duration_seconds is not None:
            segment_duration_seconds = round(total_route_duration_seconds / trip_days)

        segment_points = segment_points_between(
            decoded_points=decoded_points,
            cumulative_distances_m=cumulative_distances_m,
            start_distance_m=start_distance,
            end_distance_m=end_distance,
        )

        segments.append(
            {
                "day": day_index + 1,
                "day_label": f"Day {day_index + 1}",
                "start_distance_m": round(start_distance, 2),
                "end_distance_m": round(end_distance, 2),
                "segment_distance_m": round(segment_distance, 2),
                "segment_duration_seconds": segment_duration_seconds,
                "segment_path_points": segment_points,
                "start_point": point_at_distance(
                    decoded_points,
                    cumulative_distances_m,
                    start_distance,
                ),
                "mid_point": point_at_distance(
                    decoded_points,
                    cumulative_distances_m,
                    midpoint_distance,
                ),
                "end_point": point_at_distance(
                    decoded_points,
                    cumulative_distances_m,
                    end_distance,
                ),
                "is_overnight_stop": day_index < trip_days - 1,
            }
        )

    return segments


def segment_points_between(
    *,
    decoded_points: list[dict[str, float]],
    cumulative_distances_m: list[float],
    start_distance_m: float,
    end_distance_m: float,
    max_points: int = 80,
) -> list[dict[str, float]]:
    if not decoded_points:
        return []

    start_point = point_at_distance(
        decoded_points,
        cumulative_distances_m,
        start_distance_m,
    )
    end_point = point_at_distance(
        decoded_points,
        cumulative_distances_m,
        end_distance_m,
    )

    selected_points = [start_point]
    for point, cumulative_distance in zip(decoded_points, cumulative_distances_m):
        if start_distance_m < cumulative_distance < end_distance_m:
            selected_points.append(point)
    selected_points.append(end_point)

    if len(selected_points) <= max_points:
        return selected_points

    step = max(1, len(selected_points) // max_points)
    sampled = selected_points[::step]
    if sampled[-1] != selected_points[-1]:
        sampled.append(selected_points[-1])
    return sampled


def recommend_segment_query_plan(segment: dict[str, Any]) -> dict[str, Any]:
    segment_distance = float(segment.get("segment_distance_m", 0))
    attraction_radius_m = _clamp(segment_distance * 0.08, minimum=3_000, maximum=15_000)
    lodging_radius_m = _clamp(segment_distance * 0.06, minimum=4_000, maximum=12_000)

    return {
        "attractions": {
            "point": segment["mid_point"],
            "radius_m": attraction_radius_m,
            "max_results": 10,
        },
        "lodging": {
            "point": segment["end_point"],
            "radius_m": lodging_radius_m,
            "max_results": 3 if segment.get("is_overnight_stop") else 0,
        },
    }


def _clamp(value: float, *, minimum: float, maximum: float) -> int:
    return int(max(minimum, min(maximum, value)))
