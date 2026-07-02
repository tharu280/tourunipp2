from __future__ import annotations

import argparse
import json
from datetime import date

from clean_run.trip.resolve import ResolveTripService

from .generate import RouteGenerationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run clean_run route generation step.")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--duration", required=True)
    parser.add_argument("--start-date", default=date.today().isoformat())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    resolved = ResolveTripService().resolve(
        origin_text=args.origin,
        destination_text=args.destination,
        duration_text=args.duration,
        start_date=args.start_date,
    )
    result = RouteGenerationService().generate(resolved)
    print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
