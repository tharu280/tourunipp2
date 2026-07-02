from __future__ import annotations

import argparse
import json

from .service import FlightSearchPreferences, FlightSearchService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run clean_run flight search to Colombo.")
    parser.add_argument("--origin", required=True, help="Origin airport IATA code, for example DXB.")
    parser.add_argument("--departure-date", required=True, help="Departure date in YYYY-MM-DD format.")
    parser.add_argument("--search-mode", choices=["single_day", "week"], default="single_day")
    parser.add_argument("--passengers", type=int, default=1)
    parser.add_argument("--cabin-class", default="economy")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--total-budget-lkr", type=float, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = FlightSearchService().search(
        FlightSearchPreferences(
            origin=args.origin,
            departure_date=args.departure_date,
            search_mode=args.search_mode,
            passengers=args.passengers,
            cabin_class=args.cabin_class,
            currency=args.currency,
            total_budget_lkr=args.total_budget_lkr,
        )
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
