#!/usr/bin/env python3
"""Normalize and validate the minimal Sri Lanka accommodations dataset."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).parent
OUTPUT_PATH = DATA_DIR / "sri_lanka_accommodations.json"
SUMMARY_PATH = DATA_DIR / "accommodations_summary.md"

REQUIRED_FIELDS = (
    "id",
    "name",
    "district",
    "latitude",
    "longitude",
    "estimated_nightly_cost_lkr",
)


def normalize_price_value(value: Any) -> int | str:
    if isinstance(value, str) and value.strip().lower() == "unavailable":
        return "unavailable"
    return int(round(float(value)))


def load_existing_records() -> list[dict[str, Any]]:
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))

    if isinstance(payload, dict) and isinstance(payload.get("accommodations"), list):
        return payload["accommodations"]

    records: list[dict[str, Any]] = []
    for district in payload.get("districts", []):
        records.extend(district.get("accommodations", []))
    return records


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "id": str(record["id"]).strip(),
        "name": str(record["name"]).strip(),
        "district": str(record["district"]).strip(),
        "latitude": round(float(record["latitude"]), 6),
        "longitude": round(float(record["longitude"]), 6),
        "estimated_nightly_cost_lkr": normalize_price_value(record["estimated_nightly_cost_lkr"]),
    }
    return normalized


def validate_records(records: list[dict[str, Any]]) -> None:
    ids_seen: set[str] = set()

    for record in records:
        missing = [field for field in REQUIRED_FIELDS if record.get(field) in (None, "")]
        if missing:
            raise ValueError(f"Missing required fields {missing} for record: {record}")

        if record["id"] in ids_seen:
            raise ValueError(f"Duplicate accommodation id: {record['id']}")
        ids_seen.add(record["id"])

        if not (-90 <= float(record["latitude"]) <= 90):
            raise ValueError(f"Invalid latitude for {record['name']}")
        if not (-180 <= float(record["longitude"]) <= 180):
            raise ValueError(f"Invalid longitude for {record['name']}")
        price_value = record["estimated_nightly_cost_lkr"]
        if isinstance(price_value, str):
            if price_value.strip().lower() != "unavailable":
                raise ValueError(f"Invalid estimated_nightly_cost_lkr for {record['name']}")
        elif float(price_value) <= 0:
            raise ValueError(f"Invalid estimated_nightly_cost_lkr for {record['name']}")


def build_dataset() -> dict[str, Any]:
    records = [normalize_record(record) for record in load_existing_records()]
    records.sort(key=lambda item: (item["district"], item["name"], item["id"]))
    validate_records(records)

    district_counts = Counter(record["district"] for record in records)

    return {
        "metadata": {
            "dataset_name": "Sri Lanka Accommodation Dataset",
            "schema_version": "3.0.0",
            "generated_on": datetime.now().strftime("%Y-%m-%d"),
            "generated_by": "build_sri_lanka_accommodations.py",
            "item_count": len(records),
            "district_count": len(district_counts),
            "record_fields": list(REQUIRED_FIELDS),
            "organization": "flat",
        },
        "accommodations": records,
    }


def write_summary(dataset: dict[str, Any]) -> None:
    records = dataset["accommodations"]
    district_counts = Counter(record["district"] for record in records)

    lines = [
        "# Accommodation Summary",
        "",
        f"- Total accommodation count: **{dataset['metadata']['item_count']}**",
        f"- Districts covered: **{dataset['metadata']['district_count']}**",
        "",
        "## Minimal Record Schema",
        "",
        "- `id`",
        "- `name`",
        "- `district`",
        "- `latitude`",
        "- `longitude`",
        "- `estimated_nightly_cost_lkr`",
        "",
        "## Accommodation Count by District",
        "",
    ]

    for district, count in sorted(district_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{district}`: {count}")

    lines.extend(
        [
            "",
            "## Maintenance Notes",
            "",
            "- This dataset is intentionally minimal so nightly costs can be filled and maintained by hand.",
            "- Ranking logic uses only `estimated_nightly_cost_lkr` and distance from the overnight anchor.",
            "- `estimated_nightly_cost_lkr` may be an integer or the literal string `unavailable` during manual price review.",
            "- Keep IDs stable once the new dataset is rebuilt from your Booking-based district inputs.",
        ]
    )

    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    dataset = build_dataset()
    OUTPUT_PATH.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
    write_summary(dataset)
    print(f"Wrote {OUTPUT_PATH} with {dataset['metadata']['item_count']} accommodations and {SUMMARY_PATH.name}.")


if __name__ == "__main__":
    main()
