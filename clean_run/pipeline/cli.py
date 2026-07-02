from __future__ import annotations

import argparse
import json
from datetime import date

from .service import CleanRunPipelineService


STOP_VALUES = [
    "intake",
    "resolve_trip",
    "route_generation",
    "place_enrichment",
    "road_enrichment",
    "weather_enrichment",
    "crowd_enrichment",
    "traffic_enrichment",
    "travel_windows",
    "itinerary",
    "final",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the clean_run backend pipeline.")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--duration", required=True)
    parser.add_argument("--start-date", default=date.today().isoformat())
    parser.add_argument("--departure-time", default="08:00")
    parser.add_argument("--place-strategy", choices=["nearby", "text"], default="nearby")
    parser.add_argument("--accommodation-budget-lkr", type=float, default=None)
    parser.add_argument("--total-budget-lkr", type=float, default=None)
    parser.add_argument("--flight-usd-to-lkr-rate", type=float, default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--stop-after", choices=STOP_VALUES, default="final")
    parser.add_argument("--use-gemini-itinerary", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stop_after = None if args.stop_after == "final" else args.stop_after
    payload = CleanRunPipelineService().run(
        origin=args.origin,
        destination=args.destination,
        duration=args.duration,
        start_date=args.start_date,
        departure_time=args.departure_time,
        place_strategy=args.place_strategy,
        accommodation_budget_lkr=args.accommodation_budget_lkr,
        total_budget_lkr=args.total_budget_lkr,
        flight_usd_to_lkr_rate=args.flight_usd_to_lkr_rate,
        session_id=args.session_id,
        use_gemini_itinerary=args.use_gemini_itinerary,
        stop_after=stop_after,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
