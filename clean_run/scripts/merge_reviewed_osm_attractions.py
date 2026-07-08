from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CURATED_FILE = ROOT / "data" / "sri_lanka_attractions.json"
OSM_CANDIDATES_FILE = ROOT / "data" / "osm" / "osm_attraction_candidates.json"
OSM_REVIEW_CSV = ROOT / "data" / "osm" / "osm_attraction_review.csv"
EXPANDED_FILE = ROOT / "data" / "osm" / "expanded_sri_lanka_attractions.json"


APPROVED_REVIEW_STATUSES = {"approved", "keep", "osm_verified"}


def load_review_decisions(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    decisions: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            osm_type = row.get("osm_type", "").strip()
            osm_id = row.get("osm_id", "").strip()
            status = row.get("review_status", "").strip().lower()
            if osm_type and osm_id:
                decisions[f"{osm_type}/{osm_id}"] = status
    return decisions


def iter_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for district in payload.get("districts", []):
        candidates.extend(district.get("attractions", []))
    return candidates


def promote_candidate(candidate: dict[str, Any], review_status: str) -> dict[str, Any]:
    promoted = dict(candidate)
    promoted["source_quality"] = "osm_verified"
    promoted["planner_eligible"] = True
    promoted["review_status"] = review_status
    promoted["tags"] = sorted(set(promoted.get("tags") or []) | {"osm_verified"})
    promoted["summary"] = (
        promoted.get("summary", "")
        .replace("Requires review before planner use.", "Reviewed OSM expansion candidate.")
        .strip()
    )
    return promoted


def merge_reviewed_candidates(
    *,
    curated_file: Path = CURATED_FILE,
    candidates_file: Path = OSM_CANDIDATES_FILE,
    review_csv: Path = OSM_REVIEW_CSV,
    output_file: Path = EXPANDED_FILE,
) -> dict[str, Any]:
    curated_payload = json.loads(curated_file.read_text(encoding="utf-8"))
    candidates_payload = json.loads(candidates_file.read_text(encoding="utf-8"))
    decisions = load_review_decisions(review_csv)

    approved: list[dict[str, Any]] = []
    skipped_counts: Counter[str] = Counter()
    for candidate in iter_candidates(candidates_payload):
        osm_key = f"{candidate.get('osm_type')}/{candidate.get('osm_id')}"
        review_status = decisions.get(osm_key, candidate.get("review_status", "")).lower()
        if review_status not in APPROVED_REVIEW_STATUSES:
            skipped_counts[review_status or "missing_review_status"] += 1
            continue
        if candidate.get("duplicate_status") in {"duplicate_existing", "duplicate_osm_candidate", "reject"}:
            skipped_counts[f"blocked_{candidate.get('duplicate_status')}"] += 1
            continue
        approved.append(promote_candidate(candidate, review_status))

    by_district: dict[str, list[dict[str, Any]]] = {}
    for district in curated_payload.get("districts", []):
        by_district[district["district"]] = list(district.get("attractions", []))

    for candidate in approved:
        by_district.setdefault(candidate["district"], []).append(candidate)

    expanded_districts: list[dict[str, Any]] = []
    for district in curated_payload.get("districts", []):
        attractions = by_district[district["district"]]
        expanded_districts.append(
            {
                **district,
                "attraction_count": len(attractions),
                "attractions": attractions,
            }
        )

    curated_metadata = curated_payload.get("metadata", {})
    tier_counts = Counter()
    for district in expanded_districts:
        for attraction in district.get("attractions", []):
            tier_counts[attraction.get("tier", "unknown")] += 1

    expanded_payload = {
        "metadata": {
            **curated_metadata,
            "dataset_name": "Sri Lanka Expanded Tourist Attractions",
            "schema_version": "3.1.0-osm-expanded",
            "generated_on": datetime.now(timezone.utc).date().isoformat(),
            "generated_by": "clean_run/scripts/merge_reviewed_osm_attractions.py",
            "item_count": sum(district["attraction_count"] for district in expanded_districts),
            "tier_counts": dict(sorted(tier_counts.items())),
            "osm_promoted_count": len(approved),
            "osm_merge_policy": "Only manually reviewed OSM rows with review_status approved/keep/osm_verified are promoted.",
            "osm_skipped_counts": dict(sorted(skipped_counts.items())),
        },
        "districts": expanded_districts,
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(expanded_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return expanded_payload["metadata"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge only reviewed OSM attraction candidates into an expanded dataset.")
    parser.add_argument("--curated-file", type=Path, default=CURATED_FILE)
    parser.add_argument("--candidates-file", type=Path, default=OSM_CANDIDATES_FILE)
    parser.add_argument("--review-csv", type=Path, default=OSM_REVIEW_CSV)
    parser.add_argument("--output-file", type=Path, default=EXPANDED_FILE)
    args = parser.parse_args()
    metadata = merge_reviewed_candidates(
        curated_file=args.curated_file,
        candidates_file=args.candidates_file,
        review_csv=args.review_csv,
        output_file=args.output_file,
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
