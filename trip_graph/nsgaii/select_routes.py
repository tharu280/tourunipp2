from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TIER_WEIGHTS = {
    "tier_1": 12.0,
    "tier_2": 6.0,
    "tier_3": 2.0,
}

RISK_LEVEL_WEIGHTS = {
    "unknown": None,
    "low": 10.0,
    "medium": 45.0,
    "high": 85.0,
}

OBJECTIVE_DIRECTIONS = {
    "distance_meters": "min",
    "duration_seconds": "min",
    "road_risk_score": "min",
    "weather_risk_score": "min",
    "crowd_pressure_score": "min",
    "attraction_value_score": "max",
    "lodging_value_score": "max",
}

DEFAULT_COMPROMISE_WEIGHTS = {
    "distance_meters": 0.10,
    "duration_seconds": 0.15,
    "road_risk_score": 0.20,
    "weather_risk_score": 0.15,
    "crowd_pressure_score": 0.10,
    "attraction_value_score": 0.20,
    "lodging_value_score": 0.10,
}


@dataclass
class RouteCandidate:
    route_id: str
    route: dict[str, Any]
    objectives: dict[str, float | None]
    used_objectives: dict[str, float]
    pareto_rank: int | None = None
    crowding_distance: float = 0.0
    compromise_score: float | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rank enriched route alternatives using NSGA-II style Pareto fronts "
            "and crowding distance."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a routes/enriched-routes JSON file.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. Defaults to outputs/nsgaii-ranked-<timestamp>.json",
    )
    return parser.parse_args()


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs") / f"nsgaii-ranked-routes-{timestamp}.json"


def parse_duration_seconds(route: dict[str, Any]) -> int | None:
    duration_value = route.get("duration")
    if isinstance(duration_value, str) and duration_value.endswith("s"):
        try:
            return int(float(duration_value[:-1]))
        except ValueError:
            return None

    segment_durations = [
        int(segment.get("segment_duration_seconds") or 0)
        for segment in route.get("segments", [])
        if segment.get("segment_duration_seconds") is not None
    ]
    if segment_durations:
        return sum(segment_durations)
    return None


def score_attraction(place: dict[str, Any]) -> float:
    importance = float(place.get("importance_score") or place.get("rating") or 0.0)
    tier_weight = TIER_WEIGHTS.get(place.get("tier"), 0.0)
    tags = place.get("tags", [])
    tag_bonus = 2.0 if "must_see" in tags or "iconic" in tags else 0.0
    distance_penalty = min(float(place.get("distance_from_route_m") or place.get("distance_from_anchor_m") or 0) / 1000 * 0.5, 6.0)
    return round((importance * 2.5) + tier_weight + tag_bonus - distance_penalty, 3)


def attraction_value_score(route: dict[str, Any]) -> float | None:
    segments = route.get("segments") or []
    if not segments:
        return None

    total = 0.0
    count = 0
    for segment in segments:
        selected = segment.get("gemini_selected_attractions") or segment.get("selected_attractions")
        if not selected:
            selected = segment.get("top_attractions", [])[:3]
        for place in selected:
            total += score_attraction(place)
            count += 1

    if count == 0:
        return 0.0
    return round(total, 3)


def score_lodging(place: dict[str, Any]) -> float:
    rating = float(place.get("rating") or 0.0)
    review_count = int(place.get("user_rating_count") or 0)
    distance_penalty = min(float(place.get("distance_from_anchor_m") or 0) / 1000 * 0.4, 5.0)
    return round((rating * 5.0) + min(math.log1p(review_count) * 2.5, 10.0) - distance_penalty, 3)


def lodging_value_score(route: dict[str, Any]) -> float | None:
    segments = route.get("segments") or []
    lodging_scores = []
    for segment in segments:
        recommended = segment.get("recommended_lodging")
        if recommended:
            lodging_scores.append(score_lodging(recommended))
            continue
        top_lodging = segment.get("top_lodging") or []
        if top_lodging:
            lodging_scores.append(score_lodging(top_lodging[0]))

    if not lodging_scores:
        return None
    return round(sum(lodging_scores) / len(lodging_scores), 3)


def road_risk_score(route: dict[str, Any]) -> float | None:
    road_alerts = route.get("road_alerts") or {}
    risk_level = road_alerts.get("risk_level", "unknown")
    base = RISK_LEVEL_WEIGHTS.get(risk_level)
    if base is None:
        return None

    critical_count = int(road_alerts.get("critical_count", 0) or 0)
    total_incidents = int(road_alerts.get("total_deduplicated", 0) or 0)
    score = base + min(critical_count * 4, 10) + min(total_incidents * 1.5, 12)
    return round(score, 3)


def weather_risk_score(route: dict[str, Any]) -> float | None:
    weather_summary = route.get("weather_summary") or {}
    average_score = weather_summary.get("average_weather_risk_score")
    max_score = weather_summary.get("max_weather_risk_score")

    values = [value for value in [average_score, max_score] if value is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def crowd_pressure_score(route: dict[str, Any]) -> float | None:
    crowd_signals = route.get("crowd_signals") or {}
    score = crowd_signals.get("signal_score")
    if score is None:
        return None
    return round(float(score), 3)


def build_candidate(route: dict[str, Any]) -> RouteCandidate:
    objectives = {
        "distance_meters": float(route.get("distance_meters") or 0.0),
        "duration_seconds": parse_duration_seconds(route),
        "road_risk_score": road_risk_score(route),
        "weather_risk_score": weather_risk_score(route),
        "crowd_pressure_score": crowd_pressure_score(route),
        "attraction_value_score": attraction_value_score(route),
        "lodging_value_score": lodging_value_score(route),
    }
    return RouteCandidate(
        route_id=route.get("route_id", "unknown_route"),
        route=route,
        objectives=objectives,
        used_objectives={},
    )


def infer_active_objectives(candidates: list[RouteCandidate]) -> list[str]:
    active = []
    for objective in OBJECTIVE_DIRECTIONS:
        values = [candidate.objectives.get(objective) for candidate in candidates]
        if all(value is not None for value in values):
            active.append(objective)
    return active


def dominates(left: RouteCandidate, right: RouteCandidate, objectives: list[str]) -> bool:
    left_better_or_equal = True
    left_strictly_better = False

    for objective in objectives:
        left_value = left.used_objectives[objective]
        right_value = right.used_objectives[objective]
        direction = OBJECTIVE_DIRECTIONS[objective]

        if direction == "min":
            if left_value > right_value:
                left_better_or_equal = False
                break
            if left_value < right_value:
                left_strictly_better = True
        else:
            if left_value < right_value:
                left_better_or_equal = False
                break
            if left_value > right_value:
                left_strictly_better = True

    return left_better_or_equal and left_strictly_better


def nondominated_sort(candidates: list[RouteCandidate], objectives: list[str]) -> list[list[RouteCandidate]]:
    domination_counts: dict[str, int] = {candidate.route_id: 0 for candidate in candidates}
    dominated_sets: dict[str, list[str]] = {candidate.route_id: [] for candidate in candidates}
    candidate_map = {candidate.route_id: candidate for candidate in candidates}

    first_front: list[RouteCandidate] = []

    for left in candidates:
        for right in candidates:
            if left.route_id == right.route_id:
                continue
            if dominates(left, right, objectives):
                dominated_sets[left.route_id].append(right.route_id)
            elif dominates(right, left, objectives):
                domination_counts[left.route_id] += 1

        if domination_counts[left.route_id] == 0:
            left.pareto_rank = 1
            first_front.append(left)

    fronts: list[list[RouteCandidate]] = []
    current_front = first_front
    rank = 1

    while current_front:
        fronts.append(current_front)
        next_front: list[RouteCandidate] = []
        for candidate in current_front:
            for dominated_id in dominated_sets[candidate.route_id]:
                domination_counts[dominated_id] -= 1
                if domination_counts[dominated_id] == 0:
                    dominated_candidate = candidate_map[dominated_id]
                    dominated_candidate.pareto_rank = rank + 1
                    next_front.append(dominated_candidate)
        rank += 1
        current_front = next_front

    return fronts


def assign_crowding_distance(front: list[RouteCandidate], objectives: list[str]) -> None:
    if not front:
        return
    if len(front) <= 2:
        for candidate in front:
            candidate.crowding_distance = float("inf")
        return

    for candidate in front:
        candidate.crowding_distance = 0.0

    for objective in objectives:
        direction = OBJECTIVE_DIRECTIONS[objective]
        reverse = direction == "max"
        ordered = sorted(front, key=lambda candidate: candidate.used_objectives[objective], reverse=reverse)
        ordered[0].crowding_distance = float("inf")
        ordered[-1].crowding_distance = float("inf")

        min_value = min(candidate.used_objectives[objective] for candidate in front)
        max_value = max(candidate.used_objectives[objective] for candidate in front)
        span = max_value - min_value
        if span == 0:
            continue

        for index in range(1, len(ordered) - 1):
            if math.isinf(ordered[index].crowding_distance):
                continue

            prev_value = ordered[index - 1].used_objectives[objective]
            next_value = ordered[index + 1].used_objectives[objective]
            ordered[index].crowding_distance += abs(next_value - prev_value) / span


def normalized_value(
    *,
    value: float,
    objective: str,
    minimum: float,
    maximum: float,
) -> float:
    if maximum == minimum:
        return 1.0

    direction = OBJECTIVE_DIRECTIONS[objective]
    if direction == "max":
        return (value - minimum) / (maximum - minimum)
    return (maximum - value) / (maximum - minimum)


def assign_compromise_scores(candidates: list[RouteCandidate], objectives: list[str]) -> None:
    ranges: dict[str, tuple[float, float]] = {}
    for objective in objectives:
        values = [candidate.used_objectives[objective] for candidate in candidates]
        ranges[objective] = (min(values), max(values))

    active_weights = {
        objective: DEFAULT_COMPROMISE_WEIGHTS.get(objective, 0.0)
        for objective in objectives
    }
    total_weight = sum(active_weights.values()) or 1.0

    for candidate in candidates:
        score = 0.0
        for objective in objectives:
            minimum, maximum = ranges[objective]
            score += (
                normalized_value(
                    value=candidate.used_objectives[objective],
                    objective=objective,
                    minimum=minimum,
                    maximum=maximum,
                )
                * active_weights[objective]
            )
        candidate.compromise_score = round(score / total_weight, 6)


def route_output(candidate: RouteCandidate) -> dict[str, Any]:
    crowding_distance = candidate.crowding_distance
    if math.isinf(crowding_distance):
        crowding_distance = None

    return {
        "route_id": candidate.route_id,
        "pareto_rank": candidate.pareto_rank,
        "crowding_distance": crowding_distance,
        "compromise_score": candidate.compromise_score,
        "objectives": candidate.objectives,
        "used_objectives": candidate.used_objectives,
        "distance_meters": candidate.route.get("distance_meters"),
        "duration": candidate.route.get("duration"),
        "route_labels": candidate.route.get("route_labels", []),
    }


def build_summary(candidates: list[RouteCandidate], objectives: list[str]) -> dict[str, Any]:
    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: (
            candidate.pareto_rank or 999,
            -1 if math.isinf(candidate.crowding_distance) else -candidate.crowding_distance,
            -(candidate.compromise_score or 0),
        ),
    )
    recommended = max(
        [candidate for candidate in candidates if candidate.pareto_rank == 1],
        key=lambda candidate: (
            candidate.compromise_score or 0,
            candidate.crowding_distance if not math.isinf(candidate.crowding_distance) else 9999,
        ),
    )
    return {
        "active_objectives": objectives,
        "recommended_route_id": recommended.route_id,
        "recommended_reason": (
            "Selected from the first Pareto front using the best compromise score "
            "across the currently available objectives."
        ),
        "routes": [route_output(candidate) for candidate in sorted_candidates],
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    routes = payload.get("routes", [])
    candidates = [build_candidate(route) for route in routes]
    if not candidates:
        raise RuntimeError("Input file does not contain any routes.")

    objectives = infer_active_objectives(candidates)
    if not objectives:
        raise RuntimeError(
            "No comparable objectives were available across all routes. "
            "Make sure the route file contains route metrics or enrichments."
        )

    for candidate in candidates:
        candidate.used_objectives = {
            objective: float(candidate.objectives[objective])
            for objective in objectives
            if candidate.objectives[objective] is not None
        }

    fronts = nondominated_sort(candidates, objectives)
    for front in fronts:
        assign_crowding_distance(front, objectives)
    assign_compromise_scores(candidates, objectives)

    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selector": "nsga_ii_style_route_ranking",
        "input_file": str(input_path),
        "route_count": len(candidates),
        "summary": build_summary(candidates, objectives),
    }

    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Saved NSGA-II style route ranking to {output_path}")


if __name__ == "__main__":
    main()
