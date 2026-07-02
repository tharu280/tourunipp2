from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse
import csv
import time

import requests


BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"
CACHE_FILE = Path(__file__).resolve().parents[1] / "data" / "wiki_pageviews" / "attraction_monthly_pageviews.csv"
USER_AGENT = "TourUniPP2/0.1 (local MVP attraction demand research)"


@dataclass(frozen=True)
class MonthlyPageviewRow:
    place_id: str
    display_name: str
    wiki_title: str
    year: int
    month: int
    views: int
    source: str


def extract_wiki_title(source_urls: list[str] | None) -> str | None:
    for raw_url in source_urls or []:
        parsed = urlparse(raw_url)
        if parsed.netloc != "en.wikipedia.org" or not parsed.path.startswith("/wiki/"):
            continue
        title = parsed.path.removeprefix("/wiki/").strip("/")
        if title:
            return unquote(title)
    return None


def resolve_canonical_wiki_title(
    *,
    wiki_title: str,
    timeout: int = 30,
    max_retries: int = 3,
) -> str | None:
    response = None
    for attempt in range(max_retries + 1):
        response = requests.get(
            WIKI_API_URL,
            params={
                "action": "query",
                "format": "json",
                "redirects": 1,
                "titles": wiki_title.replace("_", " "),
            },
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=timeout,
        )
        if response.status_code != 429:
            break
        retry_after = response.headers.get("Retry-After")
        delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
        time.sleep(min(max(delay, 1), 30))

    if response is None or response.status_code in {404, 429}:
        return None
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return None
    for page in pages.values():
        if isinstance(page, dict) and "missing" not in page and page.get("title"):
            return str(page["title"]).replace(" ", "_")
    return None


def fetch_monthly_pageviews(
    *,
    wiki_title: str,
    start: str = "2024010100",
    end: str = "2026010100",
    project: str = "en.wikipedia.org",
    access: str = "all-access",
    agent: str = "user",
    timeout: int = 30,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    article = quote(wiki_title.replace(" ", "_"), safe="")
    url = f"{BASE_URL}/{project}/{access}/{agent}/{article}/monthly/{start}/{end}"

    response = None
    for attempt in range(max_retries + 1):
        response = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=timeout,
        )
        if response.status_code != 429:
            break
        retry_after = response.headers.get("Retry-After")
        delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
        time.sleep(min(max(delay, 1), 30))

    if response is None or response.status_code in {404, 429}:
        return []
    response.raise_for_status()
    data = response.json()
    items = data.get("items", [])
    return items if isinstance(items, list) else []


@lru_cache(maxsize=1)
def load_monthly_pageview_cache() -> tuple[MonthlyPageviewRow, ...]:
    if not CACHE_FILE.exists():
        return ()

    rows: list[MonthlyPageviewRow] = []
    with CACHE_FILE.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for item in reader:
            try:
                rows.append(
                    MonthlyPageviewRow(
                        place_id=item["place_id"],
                        display_name=item["display_name"],
                        wiki_title=item["wiki_title"],
                        year=int(item["year"]),
                        month=int(item["month"]),
                        views=int(item["views"]),
                        source=item.get("source") or "Wikimedia Pageviews API",
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    return tuple(rows)


def _percentile_rank(value: float, population: list[float]) -> float:
    if not population:
        return 0.0
    below_or_equal = sum(1 for item in population if item <= value)
    return round((below_or_equal / len(population)) * 100, 1)


def _score_from_percentile(percentile: float) -> int:
    if percentile >= 90:
        return 18
    if percentile >= 75:
        return 14
    if percentile >= 60:
        return 10
    if percentile >= 40:
        return 6
    return 2


def _level_from_score(score: int) -> str:
    if score >= 14:
        return "high"
    if score >= 8:
        return "medium"
    return "low"


def _find_month_row(
    *,
    place_id: str | None,
    wiki_title: str | None,
    target_date: date,
    rows: tuple[MonthlyPageviewRow, ...],
) -> MonthlyPageviewRow | None:
    matches = [
        row
        for row in rows
        if row.month == target_date.month
        and ((place_id and row.place_id == place_id) or (wiki_title and row.wiki_title == wiki_title))
    ]
    if not matches:
        return None
    if target_date.year >= 2026:
        completed_history = [row for row in matches if row.year < target_date.year]
        if completed_history:
            return max(completed_history, key=lambda row: row.year)
    exact_year = [row for row in matches if row.year == target_date.year]
    if exact_year:
        return exact_year[0]
    return max(matches, key=lambda row: row.year)


def get_attraction_monthly_interest(
    *,
    place: dict[str, Any],
    iso_date: str,
) -> dict[str, Any]:
    rows = load_monthly_pageview_cache()
    if not rows:
        return {
            "level": "unknown",
            "score": 0,
            "summary": "Wikipedia monthly pageview cache is unavailable.",
            "source": "unavailable",
            "is_seasonal_proxy": False,
        }

    target_date = date.fromisoformat(iso_date)
    wiki_title = place.get("wiki_title") or extract_wiki_title(place.get("source_urls"))
    row = _find_month_row(
        place_id=place.get("place_id"),
        wiki_title=wiki_title,
        target_date=target_date,
        rows=rows,
    )
    if row is None:
        return {
            "level": "unknown",
            "score": 0,
            "summary": "Wikipedia monthly pageviews are unavailable for this attraction.",
            "source": "unavailable",
            "is_seasonal_proxy": False,
        }

    attraction_rows = [
        item
        for item in rows
        if item.place_id == row.place_id or (wiki_title and item.wiki_title == wiki_title)
    ]
    percentile = _percentile_rank(row.views, [item.views for item in attraction_rows])
    score = _score_from_percentile(percentile)
    level = _level_from_score(score)
    is_proxy = row.year != target_date.year
    summary = (
        f"Wikipedia monthly pageviews suggest {level} seasonal interest for {row.display_name} "
        f"({row.views:,} views in {row.year}-{row.month:02d})."
    )
    if is_proxy:
        summary += " Using the latest matching month as a seasonal proxy."

    return {
        "level": level,
        "score": score,
        "summary": summary,
        "place_id": row.place_id,
        "display_name": row.display_name,
        "wiki_title": row.wiki_title,
        "date": iso_date,
        "matched_year": row.year,
        "matched_month": row.month,
        "views": row.views,
        "percentile": percentile,
        "source": row.source,
        "is_seasonal_proxy": is_proxy,
    }
