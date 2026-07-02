from __future__ import annotations

import argparse
import json
from datetime import date

from .resolve import ResolveTripService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run clean_run trip resolution step.")
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
    print(json.dumps(resolved.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
