from __future__ import annotations

from typing import Any

from clean_run.integrations.crowd_client import get_crowd_signals_for_route


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
