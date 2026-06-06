from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from google_routes.client import (
    build_route_profiles,
    compute_routes,
    save_route_profiles,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Google route alternatives and save them as JSON."
    )
    parser.add_argument("--origin-lat", type=float, required=True)
    parser.add_argument("--origin-lng", type=float, required=True)
    parser.add_argument("--destination-lat", type=float, required=True)
    parser.add_argument("--destination-lng", type=float, required=True)
    parser.add_argument("--travel-mode", default="DRIVE")
    parser.add_argument("--routing-preference", default="TRAFFIC_AWARE")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON output path. Defaults to outputs/routes-<timestamp>.json",
    )
    return parser.parse_args()


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs") / f"routes-{timestamp}.json"


def main() -> None:
    args = parse_args()
    response_payload = compute_routes(
        origin_lat=args.origin_lat,
        origin_lng=args.origin_lng,
        destination_lat=args.destination_lat,
        destination_lng=args.destination_lng,
        travel_mode=args.travel_mode,
        routing_preference=args.routing_preference,
        compute_alternative_routes=True,
    )
    route_profiles = build_route_profiles(
        response_payload=response_payload,
        origin_lat=args.origin_lat,
        origin_lng=args.origin_lng,
        destination_lat=args.destination_lat,
        destination_lng=args.destination_lng,
    )

    output_path = save_route_profiles(
        route_profiles,
        output_path=args.output or default_output_path(),
    )

    print(f"Saved {route_profiles['route_count']} routes to {output_path}")


if __name__ == "__main__":
    main()
