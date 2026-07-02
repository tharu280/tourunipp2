from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import csv
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clean_run.integrations.wiki_pageviews_client import (
    CACHE_FILE,
    extract_wiki_title,
    fetch_monthly_pageviews,
    resolve_canonical_wiki_title,
)


ATTRACTIONS_FILE = ROOT / "data" / "sri_lanka_attractions.json"
ATTEMPTS_FILE = CACHE_FILE.parent / "attraction_pageview_attempts.csv"


def _iter_attractions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    attractions: list[dict[str, Any]] = []
    for district in payload.get("districts", []):
        attractions.extend(district.get("attractions", []))
    return attractions


def _timestamp_to_year_month(timestamp: str) -> tuple[int, int]:
    return int(timestamp[:4]), int(timestamp[4:6])


def _write_cache(rows: list[dict[str, Any]]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["place_id", "display_name", "wiki_title", "year", "month", "views", "source"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_attempts(rows: list[dict[str, Any]]) -> None:
    ATTEMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ATTEMPTS_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["place_id", "display_name", "wiki_title", "status", "monthly_rows"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _load_existing_rows() -> list[dict[str, Any]]:
    if not CACHE_FILE.exists():
        return []
    with CACHE_FILE.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _load_attempt_rows() -> list[dict[str, Any]]:
    if not ATTEMPTS_FILE.exists():
        return []
    with ATTEMPTS_FILE.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def build_cache(
    *,
    limit: int | None = None,
    sleep_seconds: float = 0.2,
    save_every: int = 10,
    resume: bool = True,
) -> int:
    payload = json.loads(ATTRACTIONS_FILE.read_text(encoding="utf-8"))
    attractions = _iter_attractions(payload)
    rows: list[dict[str, Any]] = _load_existing_rows() if resume else []
    attempts: list[dict[str, Any]] = _load_attempt_rows() if resume else []
    cached_place_ids = {row.get("place_id") for row in rows if row.get("place_id")}
    attempted_place_ids = {row.get("place_id") for row in attempts if row.get("place_id")}
    processed = 0
    fetchable_attractions = [
        attraction
        for attraction in attractions
        if extract_wiki_title(attraction.get("source_urls"))
        and (not resume or attraction.get("id") not in cached_place_ids)
        and (not resume or attraction.get("id") not in attempted_place_ids)
    ]
    available = len(fetchable_attractions)

    for attraction in fetchable_attractions:
        wiki_title = extract_wiki_title(attraction.get("source_urls"))
        if not wiki_title:
            continue
        if limit is not None and processed >= limit:
            break

        items = fetch_monthly_pageviews(wiki_title=wiki_title)
        resolved_title = wiki_title
        status = "ok" if items else "no_data"
        if not items:
            canonical_title = resolve_canonical_wiki_title(wiki_title=wiki_title)
            if canonical_title and canonical_title != wiki_title:
                canonical_items = fetch_monthly_pageviews(wiki_title=canonical_title)
                if canonical_items:
                    resolved_title = canonical_title
                    items = canonical_items
                    status = "ok_resolved"

        processed += 1
        print(
            f"[{processed}/{limit or available}] {attraction.get('name')} -> {len(items)} monthly rows ({status})",
            flush=True,
        )
        attempts.append(
            {
                "place_id": attraction.get("id"),
                "display_name": attraction.get("name"),
                "wiki_title": resolved_title,
                "status": status,
                "monthly_rows": len(items),
            }
        )
        time.sleep(sleep_seconds)

        for item in items:
            timestamp = str(item.get("timestamp", ""))
            if len(timestamp) < 6:
                continue
            year, month = _timestamp_to_year_month(timestamp)
            rows.append(
                {
                    "place_id": attraction.get("id"),
                    "display_name": attraction.get("name"),
                    "wiki_title": resolved_title,
                    "year": year,
                    "month": month,
                    "views": int(item.get("views", 0) or 0),
                    "source": "Wikimedia Pageviews API monthly per-article",
                }
            )

        if save_every > 0 and processed % save_every == 0:
            _write_cache(rows)
            _write_attempts(attempts)

    _write_cache(rows)
    _write_attempts(attempts)

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build monthly Wikipedia pageview cache for attractions.")
    parser.add_argument("--limit", type=int, default=None, help="Limit attractions fetched, useful for smoke tests.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between Wikimedia API requests.")
    parser.add_argument("--save-every", type=int, default=10, help="Write partial cache after this many attractions.")
    parser.add_argument("--restart", action="store_true", help="Ignore the existing cache and rebuild from scratch.")
    args = parser.parse_args()
    count = build_cache(
        limit=args.limit,
        sleep_seconds=args.sleep,
        save_every=args.save_every,
        resume=not args.restart,
    )
    print(f"Wrote {count} monthly pageview rows to {CACHE_FILE}")


if __name__ == "__main__":
    main()
