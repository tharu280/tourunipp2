from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gemini_refine.client import generate_structured_json


REFINEMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recommended_place_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "rejected_place_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "summary": {"type": "string"},
        "reasoning": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "place_id": {"type": "string"},
                    "verdict": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["place_id", "verdict", "reason"],
                "propertyOrdering": ["place_id", "verdict", "reason"],
            },
        },
    },
    "required": [
        "recommended_place_ids",
        "rejected_place_ids",
        "summary",
        "reasoning",
    ],
    "propertyOrdering": [
        "recommended_place_ids",
        "rejected_place_ids",
        "summary",
        "reasoning",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refine ranked daily attraction candidates with Gemini."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to an enriched routes JSON produced by google_places.enrich_routes.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. Defaults to outputs/gemini-refined-<timestamp>.json",
    )
    return parser.parse_args()


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs") / f"gemini-refined-routes-{timestamp}.json"


def build_prompt(
    *,
    route_id: str,
    day: int,
    trip_days: int,
    attractions: list[dict[str, Any]],
) -> str:
    attraction_lines = []
    for item in attractions:
        attraction_lines.append(
            json.dumps(
                {
                    "place_id": item.get("place_id"),
                    "name": item.get("display_name"),
                    "address": item.get("formatted_address"),
                    "rating": item.get("rating"),
                    "user_rating_count": item.get("user_rating_count"),
                    "distance_from_anchor_m": item.get("distance_from_anchor_m"),
                    "primary_type": item.get("primary_type"),
                    "types": item.get("types", []),
                    "score": item.get("score"),
                },
                ensure_ascii=False,
            )
        )

    return (
        "You are helping build a Sri Lanka tourist itinerary planner.\n"
        f"Route id: {route_id}\n"
        f"Trip day: {day} of {trip_days}\n"
        "Below is a shortlist of nearby attraction candidates that were already filtered and scored.\n"
        "Choose the attractions that are actually worth recommending for a tourist day plan.\n"
        "Prefer meaningful sightseeing places and avoid redundant, generic, or weak attractions.\n"
        "Return JSON only.\n\n"
        "Candidate attractions:\n"
        + "\n".join(attraction_lines)
    )


def refine_segment(
    *,
    route_id: str,
    trip_days: int,
    segment: dict[str, Any],
) -> dict[str, Any]:
    attractions = segment.get("top_attractions", [])
    if not attractions:
        return {
            **segment,
            "gemini_refinement": {
                "recommended_place_ids": [],
                "rejected_place_ids": [],
                "summary": "No attraction candidates were available to refine.",
                "reasoning": [],
            },
            "gemini_selected_attractions": [],
        }

    prompt = build_prompt(
        route_id=route_id,
        day=segment["day"],
        trip_days=trip_days,
        attractions=attractions,
    )
    gemini_result = generate_structured_json(
        prompt=prompt,
        response_schema=REFINEMENT_SCHEMA,
    )

    recommended_ids = set(gemini_result.get("recommended_place_ids", []))
    selected_attractions = [
        place for place in attractions if place.get("place_id") in recommended_ids
    ]

    return {
        **segment,
        "gemini_refinement": gemini_result,
        "gemini_selected_attractions": selected_attractions,
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))

    for route in data.get("routes", []):
        route["segments"] = [
            refine_segment(
                route_id=route["route_id"],
                trip_days=data.get("trip_days", route.get("trip_days", 1)),
                segment=segment,
            )
            for segment in route.get("segments", [])
        ]

    data["gemini_refined_at_utc"] = datetime.now(timezone.utc).isoformat()

    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved Gemini-refined routes to {output_path}")


if __name__ == "__main__":
    main()
