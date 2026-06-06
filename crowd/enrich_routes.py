from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crowd.client import get_crowd_signals_for_route


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich saved route files with crowd/trip-pressure signals."
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
        help="Optional output path. Defaults to outputs/crowd-enriched-<timestamp>.json",
    )
    return parser.parse_args()


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs") / f"crowd-enriched-routes-{timestamp}.json"


def infer_trip_days(payload: dict[str, Any], explicit_trip_days: int | None) -> int:
    if explicit_trip_days is not None:
        return max(explicit_trip_days, 1)
    payload_days = payload.get("trip_days")
    if isinstance(payload_days, int) and payload_days > 0:
        return payload_days
    return 1


def enrich_route(
    *,
    route: dict[str, Any],
    start_date: str,
    trip_days: int,
) -> dict[str, Any]:
    return {
        **route,
        "crowd_signals": get_crowd_signals_for_route(
            route=route,
            start_date=start_date,
            trip_days=trip_days,
        ),
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    trip_days = infer_trip_days(payload, args.trip_days)
    enriched_routes = [
        enrich_route(
            route=route,
            start_date=args.start_date,
            trip_days=trip_days,
        )
        for route in payload.get("routes", [])
    ]

    output = {
        **payload,
        "trip_days": trip_days,
        "crowd_enriched_at_utc": datetime.now(timezone.utc).isoformat(),
        "routes": enriched_routes,
    }

    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved crowd-enriched routes to {output_path}")


if __name__ == "__main__":
    main()
