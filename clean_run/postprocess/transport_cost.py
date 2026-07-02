from __future__ import annotations

import csv
from functools import lru_cache
from math import ceil
from pathlib import Path
from typing import Any


DEFAULT_BUS_BASE_FARE_LKR = 40.0
DEFAULT_BUS_PER_KM_LKR = 4.5
BUS_FARE_TABLE_PATH = Path(__file__).resolve().parents[1] / "data" / "bus_fares_normal_2026.csv"


def _round_lkr(value: float) -> int:
    return int(round(value / 10.0) * 10)


def _segment_name(segment: dict[str, Any], fallback: str) -> str:
    day_label = segment.get("day_label")
    if day_label:
        return str(day_label)
    day = segment.get("day")
    if day:
        return f"Day {day}"
    return fallback


@lru_cache(maxsize=1)
def _load_bus_fare_table() -> dict[int, dict[str, Any]]:
    if not BUS_FARE_TABLE_PATH.exists():
        return {}

    fares: dict[int, dict[str, Any]] = {}
    with BUS_FARE_TABLE_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                stage = int(row["stage"])
                fares[stage] = {
                    "stage": stage,
                    "approx_distance_km": float(row.get("approx_distance_km") or stage),
                    "current_fare_lkr": int(float(row["current_fare_lkr"])),
                    "new_fare_lkr": int(float(row["new_fare_lkr"])),
                    "effective_from": row.get("effective_from"),
                    "service_type": row.get("service_type") or "normal",
                    "source": row.get("source") or BUS_FARE_TABLE_PATH.name,
                }
            except (KeyError, TypeError, ValueError):
                continue
    return fares


def estimate_bus_fare_for_distance_km(distance_km: float) -> int:
    if distance_km <= 0:
        return 0
    fare_row = fare_band_for_distance_km(distance_km)
    if fare_row:
        return int(fare_row["new_fare_lkr"])
    fare = DEFAULT_BUS_BASE_FARE_LKR + (distance_km * DEFAULT_BUS_PER_KM_LKR)
    return max(_round_lkr(fare), int(DEFAULT_BUS_BASE_FARE_LKR))


def fare_band_for_distance_km(distance_km: float) -> dict[str, Any] | None:
    if distance_km <= 0:
        return None
    fares = _load_bus_fare_table()
    if not fares:
        return None
    max_stage = max(fares)
    stage = max(1, min(ceil(distance_km), max_stage))
    return fares.get(stage)


def estimate_transport_cost_for_route(route: dict[str, Any]) -> dict[str, Any]:
    segments = route.get("segments") or []
    segment_costs: list[dict[str, Any]] = []
    fare_table_loaded = bool(_load_bus_fare_table())
    route_distance_m = float(route.get("distance_meters") or route.get("geometry_distance_m") or 0)
    route_distance_km = round(route_distance_m / 1000.0, 1) if route_distance_m > 0 else 0.0

    raw_segment_distances_km: list[float] = []
    if segments:
        for segment in segments:
            raw_segment_distances_km.append(round(float(segment.get("segment_distance_m") or 0) / 1000.0, 1))

    raw_segment_total_km = round(sum(raw_segment_distances_km), 1)
    distance_scale = 1.0
    distance_basis = "segment_distance"
    if segments and route_distance_km > 0 and raw_segment_total_km > 0:
        divergence_ratio = abs(raw_segment_total_km - route_distance_km) / route_distance_km
        if divergence_ratio > 0.12:
            distance_scale = route_distance_km / raw_segment_total_km
            distance_basis = "scaled_to_full_route_distance"

    if segments:
        for index, segment in enumerate(segments, start=1):
            raw_distance_km = raw_segment_distances_km[index - 1] if index <= len(raw_segment_distances_km) else 0.0
            distance_km = round(raw_distance_km * distance_scale, 1)
            fare_band = fare_band_for_distance_km(distance_km)
            fare_lkr = estimate_bus_fare_for_distance_km(distance_km)
            segment_costs.append(
                {
                    "label": _segment_name(segment, f"Segment {index}"),
                    "day": segment.get("day"),
                    "distance_km": distance_km,
                    "raw_segment_distance_km": raw_distance_km,
                    "fare_stage": fare_band.get("stage") if fare_band else None,
                    "estimated_fare_lkr": fare_lkr,
                    "fare_band": fare_band,
                }
            )
    else:
        distance_m = float(route.get("distance_meters") or 0)
        distance_km = round(distance_m / 1000.0, 1)
        fare_band = fare_band_for_distance_km(distance_km)
        segment_costs.append(
            {
                "label": "Full route",
                "day": None,
                "distance_km": distance_km,
                "fare_stage": fare_band.get("stage") if fare_band else None,
                "estimated_fare_lkr": estimate_bus_fare_for_distance_km(distance_km),
                "fare_band": fare_band,
            }
        )

    total_lkr = sum(item["estimated_fare_lkr"] for item in segment_costs)
    total_distance_km = round(sum(float(item["distance_km"]) for item in segment_costs), 1)

    return {
        "mode": "bus",
        "estimated_total_lkr": total_lkr,
        "total_distance_km": total_distance_km,
        "route_distance_km": route_distance_km or total_distance_km,
        "raw_segment_total_distance_km": raw_segment_total_km or total_distance_km,
        "distance_basis": distance_basis,
        "distance_scale": round(distance_scale, 4),
        "segments": segment_costs,
        "confidence": "high" if fare_table_loaded and total_lkr > 0 else ("medium" if total_lkr > 0 else "low"),
        "source": "ntc_normal_service_fare_stage_table_2026" if fare_table_loaded else "distance_based_default_estimate",
        "formula": {
            "method": "ceil_distance_km_to_fare_stage" if fare_table_loaded else "base_plus_per_km",
            "base_fare_lkr": None if fare_table_loaded else DEFAULT_BUS_BASE_FARE_LKR,
            "per_km_lkr": None if fare_table_loaded else DEFAULT_BUS_PER_KM_LKR,
            "rounding": "ceil_to_next_stage" if fare_table_loaded else "nearest_10_lkr",
            "max_stage": max(_load_bus_fare_table()) if fare_table_loaded else None,
            "fare_table": str(BUS_FARE_TABLE_PATH) if fare_table_loaded else None,
        },
        "notes": [
            "Uses the normal service fare-stage table effective from 2026-03-24." if fare_table_loaded else "This is a planning estimate until official bus fare bands are added.",
            "Distance is mapped to fare stage with ceil(distance_km); exact route-specific bus stages can refine this later.",
            "Segment distances were scaled to match the full route distance." if distance_basis == "scaled_to_full_route_distance" else "Segment distances matched the full route distance.",
        ],
    }
