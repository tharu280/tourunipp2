from __future__ import annotations

from typing import Any

from clean_run.integrations.roadlk_client import get_road_alerts_for_route


def enrich_route(route: dict[str, Any]) -> dict[str, Any]:
    return {
        **route,
        "road_alerts": get_road_alerts_for_route(route),
    }
