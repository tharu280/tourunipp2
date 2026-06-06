from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roadlk.client import get_road_alerts_for_route


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich saved route files with RoadLK route-corridor incident summaries."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a saved routes JSON file.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. Defaults to outputs/roadlk-enriched-<timestamp>.json",
    )
    return parser.parse_args()


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs") / f"roadlk-enriched-routes-{timestamp}.json"


def enrich_route(route: dict[str, Any]) -> dict[str, Any]:
    return {
        **route,
        "road_alerts": get_road_alerts_for_route(route),
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    routes = payload.get("routes", [])
    enriched_routes = [enrich_route(route) for route in routes]

    output = {
        **payload,
        "roadlk_enriched_at_utc": datetime.now(timezone.utc).isoformat(),
        "routes": enriched_routes,
    }

    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved RoadLK-enriched routes to {output_path}")


if __name__ == "__main__":
    main()
