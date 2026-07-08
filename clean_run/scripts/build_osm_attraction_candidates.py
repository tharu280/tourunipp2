from __future__ import annotations

import argparse
import csv
import difflib
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


ATTRACTIONS_FILE = ROOT / "data" / "sri_lanka_attractions.json"
OUTPUT_DIR = ROOT / "data" / "osm"
CANDIDATES_JSON = OUTPUT_DIR / "osm_attraction_candidates.json"
REVIEW_CSV = OUTPUT_DIR / "osm_attraction_review.csv"
SUMMARY_JSON = OUTPUT_DIR / "osm_attraction_summary.json"
RAW_DIR = OUTPUT_DIR / "raw_overpass"


DISTRICTS: list[tuple[str, str, int]] = [
    ("Ampara", "Eastern", 5351718),
    ("Anuradhapura", "North Central", 5351719),
    ("Badulla", "Uva", 5351720),
    ("Batticaloa", "Eastern", 5351721),
    ("Colombo", "Western", 5351774),
    ("Galle", "Southern", 5337914),
    ("Gampaha", "Western", 5351775),
    ("Hambantota", "Southern", 5337945),
    ("Jaffna", "Northern", 3237345),
    ("Kalutara", "Western", 5351776),
    ("Kandy", "Central", 5351794),
    ("Kegalle", "Sabaragamuwa", 5351777),
    ("Kilinochchi", "Northern", 3237346),
    ("Kurunegala", "North Western", 5351778),
    ("Mannar", "Northern", 3237347),
    ("Matale", "Central", 5351795),
    ("Matara", "Southern", 5337946),
    ("Monaragala", "Uva", 5351722),
    ("Mullaitivu", "Northern", 3237348),
    ("Nuwara Eliya", "Central", 5351796),
    ("Polonnaruwa", "North Central", 5351723),
    ("Puttalam", "North Western", 5351779),
    ("Ratnapura", "Sabaragamuwa", 5351780),
    ("Trincomalee", "Eastern", 5620836),
    ("Vavuniya", "Northern", 3237349),
]


OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


STRICT_QUERY_BODY = r"""
  nwr(area.a)["tourism"~"^(attraction|viewpoint|museum|gallery|zoo|aquarium|theme_park|picnic_site|artwork)$"];
  nwr(area.a)["historic"];
  nwr(area.a)["natural"~"^(beach|peak|waterfall|cave_entrance|spring|cliff|rock|bay)$"];
  nwr(area.a)["waterway"="waterfall"];
  nwr(area.a)["leisure"~"^(park|nature_reserve|garden)$"];
"""


REJECT_NAME_PATTERNS = [
    r"^\d+$",
    r"^unknown$",
    r"^unnamed$",
    r"^bus stop$",
    r"^toilet",
    r"^parking",
]


WEAK_GENERIC_NAMES = {
    "temple",
    "mosque",
    "church",
    "kovil",
    "buddha statue",
    "statue",
    "park",
    "beach",
    "viewpoint",
}


BAD_GEOGRAPHIC_NAMES = {
    "arabian sea",
    "bay of bengal",
    "gulf of mannar",
    "indian ocean",
    "laccadive sea",
    "palk bay",
    "palk strait",
    "sri lanka",
}


NAME_STOP_WORDS = {
    "and",
    "at",
    "de",
    "of",
    "old",
    "the",
}


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def normalize_name(value: str) -> str:
    value = value.lower()
    value = value.replace("&", " and ")
    value = re.sub(r"\b(sri|shri|st|saint|the)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def name_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize_name(value).split()
        if token not in NAME_STOP_WORDS and len(token) > 1
    }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_curated_attractions() -> list[dict[str, Any]]:
    payload = json.loads(ATTRACTIONS_FILE.read_text(encoding="utf-8"))
    attractions: list[dict[str, Any]] = []
    for district in payload.get("districts", []):
        attractions.extend(district.get("attractions", []))
    return attractions


def build_overpass_query(relation_id: int) -> str:
    area_id = 3_600_000_000 + relation_id
    return f"""[out:json][timeout:120];
area({area_id})->.a;
(
{STRICT_QUERY_BODY}
);
out tags center qt;
"""


def fetch_overpass(query: str, *, sleep_seconds: float, attempts: int = 2) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                request = urllib.request.Request(
                    endpoint,
                    data=urllib.parse.urlencode({"data": query}).encode(),
                    headers={"User-Agent": "TourUni OSM candidate builder/1.0"},
                )
                with urllib.request.urlopen(request, timeout=180) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                time.sleep(sleep_seconds)
                return payload
            except Exception as exc:  # pragma: no cover - endpoint behavior is external.
                last_error = exc
                backoff = max(sleep_seconds, 2.0) * attempt
                time.sleep(backoff)
    raise RuntimeError(f"All Overpass endpoints failed: {last_error}")


def element_coordinates(element: dict[str, Any]) -> tuple[float | None, float | None]:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None, None


def osm_url(osm_type: str, osm_id: int | str) -> str:
    return f"https://www.openstreetmap.org/{osm_type}/{osm_id}"


def wikipedia_url_from_tag(tag_value: str) -> str | None:
    if not tag_value:
        return None
    title = tag_value.split(":", 1)[-1].strip().replace(" ", "_")
    if not title:
        return None
    return f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}"


def categories_from_tags(tags: dict[str, str]) -> list[str]:
    categories: set[str] = set()
    tourism = tags.get("tourism", "")
    historic = tags.get("historic", "")
    natural = tags.get("natural", "")
    leisure = tags.get("leisure", "")
    amenity = tags.get("amenity", "")
    waterway = tags.get("waterway", "")

    if tourism in {"museum", "gallery"}:
        categories.update(["museum", "cultural"])
    if tourism in {"viewpoint", "attraction", "artwork"}:
        categories.update(["scenic", "cultural"])
    if tourism in {"zoo", "aquarium"}:
        categories.update(["family", "wildlife"])
    if tourism in {"theme_park", "picnic_site"}:
        categories.update(["family", "adventure"])
    if historic:
        categories.update(["historic", "cultural"])
    if natural in {"beach", "bay"}:
        categories.update(["beach", "scenic"])
    if natural in {"peak", "cliff", "rock", "cave_entrance"}:
        categories.update(["nature", "scenic", "adventure"])
    if natural == "waterfall" or waterway == "waterfall":
        categories.update(["waterfall", "nature", "scenic"])
    if leisure in {"park", "garden"}:
        categories.update(["family", "nature"])
    if leisure == "nature_reserve":
        categories.update(["nature", "wildlife"])
    if amenity == "place_of_worship":
        categories.update(["religious", "cultural"])

    return sorted(categories) or ["scenic"]


def tags_from_osm(tags: dict[str, str], *, duplicate_status: str) -> list[str]:
    result: set[str] = {"osm_candidate"}
    if tags.get("wikidata") or tags.get("wikipedia"):
        result.add("externally_linked")
    if tags.get("tourism") in {"attraction", "viewpoint", "museum"}:
        result.add("tourism_tagged")
    if tags.get("historic"):
        result.add("historic")
    if tags.get("natural") or tags.get("waterway") == "waterfall":
        result.add("nature")
    if duplicate_status == "duplicate_existing":
        result.add("possible_duplicate")
    return sorted(result)


def quality_score(name: str, tags: dict[str, str]) -> int:
    score = 0
    tourism = tags.get("tourism")
    historic = tags.get("historic")
    natural = tags.get("natural")
    leisure = tags.get("leisure")

    if tourism == "attraction":
        score += 35
    elif tourism in {"viewpoint", "museum", "gallery", "zoo", "aquarium", "theme_park"}:
        score += 30
    elif tourism in {"picnic_site", "artwork"}:
        score += 18

    if historic:
        score += 26
    if natural in {"waterfall", "beach", "peak", "cave_entrance", "cliff", "rock", "bay"}:
        score += 24
    if tags.get("waterway") == "waterfall":
        score += 24
    if leisure in {"nature_reserve", "garden"}:
        score += 18
    elif leisure == "park":
        score += 10

    if tags.get("wikidata"):
        score += 18
    if tags.get("wikipedia"):
        score += 18
    if tags.get("website") or tags.get("contact:website"):
        score += 8
    if tags.get("name:en"):
        score += 5

    normalized = normalize_name(name)
    if len(normalized.split()) >= 2:
        score += 6
    if normalized in WEAK_GENERIC_NAMES:
        score -= 20
    if tags.get("amenity") == "place_of_worship" and not (tags.get("wikidata") or tags.get("wikipedia")):
        score -= 12

    return max(min(score, 100), 0)


def importance_from_quality(score: int) -> int:
    if score >= 80:
        return 7
    if score >= 65:
        return 6
    if score >= 45:
        return 5
    if score >= 30:
        return 4
    return 3


def tier_from_quality(score: int) -> str:
    if score >= 85:
        return "tier_2"
    return "tier_3"


def visit_hours_from_categories(categories: list[str]) -> float:
    if "wildlife" in categories:
        return 3.0
    if "waterfall" in categories or "adventure" in categories:
        return 2.0
    if "museum" in categories or "historic" in categories:
        return 1.5
    return 1.0


def reject_reason(name: str, tags: dict[str, str], lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return "missing_coordinates"
    if not name.strip():
        return "missing_name"
    normalized = normalize_name(name)
    if not normalized:
        return "missing_name"
    if normalized in BAD_GEOGRAPHIC_NAMES:
        return "large_geographic_feature"
    for pattern in REJECT_NAME_PATTERNS:
        if re.search(pattern, normalized):
            return "generic_or_invalid_name"
    if normalized in WEAK_GENERIC_NAMES and not (tags.get("wikidata") or tags.get("wikipedia")):
        return "generic_name_without_external_reference"
    return None


def find_curated_duplicate(
    *,
    name: str,
    lat: float,
    lon: float,
    curated_attractions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    normalized = normalize_name(name)
    best: dict[str, Any] | None = None

    for attraction in curated_attractions:
        curated_name = attraction.get("name", "")
        curated_norm = normalize_name(curated_name)
        if not curated_norm:
            continue
        distance = haversine_km(
            lat,
            lon,
            float(attraction.get("latitude")),
            float(attraction.get("longitude")),
        )
        ratio = difflib.SequenceMatcher(None, normalized, curated_norm).ratio()
        current_tokens = name_tokens(normalized)
        curated_tokens = name_tokens(curated_norm)
        token_overlap = bool(current_tokens & curated_tokens)
        token_jaccard = 0.0
        if current_tokens and curated_tokens:
            token_jaccard = len(current_tokens & curated_tokens) / len(current_tokens | curated_tokens)
        duplicate = (
            (ratio >= 0.88 and distance <= 5.0)
            or (token_jaccard >= 0.75 and distance <= 5.0)
            or (token_jaccard >= 0.60 and distance <= 1.0 and len(current_tokens & curated_tokens) >= 2)
            or (ratio >= 0.72 and distance <= 1.0 and token_overlap)
            or (normalized in curated_norm and distance <= 2.0 and len(normalized) >= 8)
            or (curated_norm in normalized and distance <= 2.0 and len(curated_norm) >= 8)
        )
        if not duplicate:
            continue
        candidate = {
            "id": attraction.get("id"),
            "name": curated_name,
            "distance_km": round(distance, 3),
            "similarity": round(ratio, 3),
        }
        if best is None or (candidate["similarity"], -candidate["distance_km"]) > (
            best["similarity"],
            -best["distance_km"],
        ):
            best = candidate

    return best


def quality_status(score: int, duplicate: dict[str, Any] | None, rejection: str | None) -> tuple[str, str, bool]:
    if rejection:
        return "reject", "rejected", False
    if duplicate:
        return "duplicate_existing", "duplicate", False
    if score >= 70:
        return "strong_new_candidate", "unreviewed", False
    if score >= 45:
        return "medium_candidate", "unreviewed", False
    return "weak_candidate", "unreviewed", False


def build_candidate(
    *,
    element: dict[str, Any],
    district: str,
    province: str,
    curated_attractions: list[dict[str, Any]],
) -> dict[str, Any]:
    tags = {str(k): str(v) for k, v in (element.get("tags") or {}).items()}
    name = tags.get("name:en") or tags.get("name") or tags.get("alt_name") or ""
    lat, lon = element_coordinates(element)
    rejection = reject_reason(name, tags, lat, lon)

    duplicate = None
    if rejection is None and lat is not None and lon is not None:
        duplicate = find_curated_duplicate(
            name=name,
            lat=lat,
            lon=lon,
            curated_attractions=curated_attractions,
        )

    score = quality_score(name, tags) if rejection is None else 0
    duplicate_status, review_status, planner_eligible = quality_status(score, duplicate, rejection)
    categories = categories_from_tags(tags)
    osm_type = element.get("type", "node")
    osm_id = element.get("id")
    source_urls = [osm_url(osm_type, osm_id)]
    wiki_url = wikipedia_url_from_tag(tags.get("wikipedia", ""))
    if wiki_url:
        source_urls.append(wiki_url)
    if tags.get("wikidata"):
        source_urls.append(f"https://www.wikidata.org/wiki/{tags['wikidata']}")

    candidate_id = f"lk_{slugify(district)}_osm_{osm_type}_{osm_id}"
    summary = (
        f"OSM-discovered {', '.join(categories)} candidate in {district}. "
        "Requires review before planner use."
    )
    if rejection:
        summary = f"Rejected OSM candidate in {district}: {rejection}."

    return {
        "name": name,
        "district": district,
        "province": province,
        "categories": categories,
        "latitude": lat,
        "longitude": lon,
        "importance_score": importance_from_quality(score),
        "estimated_visit_hours": visit_hours_from_categories(categories),
        "tier": tier_from_quality(score),
        "tags": tags_from_osm(tags, duplicate_status=duplicate_status),
        "summary": summary,
        "source_urls": source_urls,
        "id": candidate_id,
        "source": "osm",
        "source_quality": "osm_candidate",
        "planner_eligible": planner_eligible,
        "review_status": review_status,
        "duplicate_status": duplicate_status,
        "duplicate_of": duplicate,
        "rejection_reason": rejection,
        "osm_quality_score": score,
        "osm_type": osm_type,
        "osm_id": str(osm_id),
        "osm_tags": tags,
    }


def dedupe_osm_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        key = (candidate["district"], normalize_name(candidate.get("name", "")))
        grouped[key].append(candidate)

    result: list[dict[str, Any]] = []
    for group in grouped.values():
        if len(group) == 1:
            result.extend(group)
            continue
        ranked = sorted(
            group,
            key=lambda item: (
                item.get("duplicate_status") == "reject",
                -int(item.get("osm_quality_score", 0)),
                item.get("osm_type") != "node",
            ),
        )
        winner = ranked[0]
        result.append(winner)
        for duplicate in ranked[1:]:
            duplicate["duplicate_status"] = "duplicate_osm_candidate"
            duplicate["review_status"] = "duplicate"
            duplicate["planner_eligible"] = False
            duplicate["duplicate_of"] = {
                "id": winner.get("id"),
                "name": winner.get("name"),
                "distance_km": None,
                "similarity": 1.0,
            }
            result.append(duplicate)

    return result


def write_outputs(
    candidates: list[dict[str, Any]],
    *,
    raw_counts: dict[str, int],
    fetch_errors: dict[str, str],
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    by_district: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_district[candidate["district"]].append(candidate)

    districts_payload = []
    for district, province, _relation_id in DISTRICTS:
        district_candidates = sorted(
            by_district.get(district, []),
            key=lambda item: (
                item.get("review_status") == "rejected",
                item.get("duplicate_status") not in {"strong_new_candidate", "medium_candidate"},
                -int(item.get("osm_quality_score", 0)),
                item.get("name") or "",
            ),
        )
        districts_payload.append(
            {
                "district": district,
                "province": province,
                "attraction_count": len(district_candidates),
                "attractions": district_candidates,
            }
        )

    status_counts: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        status_counts[candidate["duplicate_status"]] += 1

    metadata = {
        "dataset_name": "Sri Lanka OSM Attraction Candidates",
        "schema_version": "0.1.0",
        "generated_on": datetime.now(timezone.utc).date().isoformat(),
        "generated_by": "clean_run/scripts/build_osm_attraction_candidates.py",
        "country": "Sri Lanka",
        "organization": "district",
        "item_count": len(candidates),
        "district_count": len(DISTRICTS),
        "source": "OpenStreetMap via Overpass API",
        "planner_policy": "Do not use raw OSM candidates for planning until manually reviewed and promoted.",
        "candidate_fields": [
            "source",
            "source_quality",
            "planner_eligible",
            "review_status",
            "duplicate_status",
            "duplicate_of",
            "rejection_reason",
            "osm_quality_score",
            "osm_type",
            "osm_id",
            "osm_tags",
        ],
        "status_counts": dict(sorted(status_counts.items())),
        "raw_overpass_counts": raw_counts,
        "fetch_errors": fetch_errors,
    }
    CANDIDATES_JSON.write_text(
        json.dumps({"metadata": metadata, "districts": districts_payload}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    fieldnames = [
        "review_status",
        "duplicate_status",
        "planner_eligible",
        "district",
        "name",
        "categories",
        "latitude",
        "longitude",
        "osm_quality_score",
        "importance_score",
        "tier",
        "duplicate_of_name",
        "duplicate_distance_km",
        "rejection_reason",
        "osm_type",
        "osm_id",
        "osm_url",
        "osm_tags",
    ]
    with REVIEW_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in sorted(
            candidates,
            key=lambda item: (
                item["district"],
                item.get("review_status") == "rejected",
                item.get("duplicate_status"),
                -int(item.get("osm_quality_score", 0)),
                item.get("name") or "",
            ),
        ):
            duplicate = candidate.get("duplicate_of") or {}
            writer.writerow(
                {
                    "review_status": candidate.get("review_status"),
                    "duplicate_status": candidate.get("duplicate_status"),
                    "planner_eligible": candidate.get("planner_eligible"),
                    "district": candidate.get("district"),
                    "name": candidate.get("name"),
                    "categories": "|".join(candidate.get("categories") or []),
                    "latitude": candidate.get("latitude"),
                    "longitude": candidate.get("longitude"),
                    "osm_quality_score": candidate.get("osm_quality_score"),
                    "importance_score": candidate.get("importance_score"),
                    "tier": candidate.get("tier"),
                    "duplicate_of_name": duplicate.get("name"),
                    "duplicate_distance_km": duplicate.get("distance_km"),
                    "rejection_reason": candidate.get("rejection_reason"),
                    "osm_type": candidate.get("osm_type"),
                    "osm_id": candidate.get("osm_id"),
                    "osm_url": candidate.get("source_urls", [""])[0],
                    "osm_tags": json.dumps(candidate.get("osm_tags") or {}, ensure_ascii=False, sort_keys=True),
                }
            )

    summary = {
        "candidate_json": str(CANDIDATES_JSON),
        "review_csv": str(REVIEW_CSV),
        "total_candidates": len(candidates),
        "status_counts": dict(sorted(status_counts.items())),
        "fetch_errors": fetch_errors,
        "district_counts": {
            district: len(by_district.get(district, [])) for district, _province, _relation_id in DISTRICTS
        },
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def load_raw_or_fetch(
    *,
    district: str,
    relation_id: int,
    sleep_seconds: float,
    refresh: bool,
) -> dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{slugify(district)}.json"
    if raw_path.exists() and not refresh:
        return json.loads(raw_path.read_text(encoding="utf-8"))

    payload = fetch_overpass(build_overpass_query(relation_id), sleep_seconds=sleep_seconds)
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def build_candidates(
    *,
    districts: list[str] | None,
    refresh: bool,
    sleep_seconds: float,
    limit_per_district: int | None,
) -> list[dict[str, Any]]:
    curated_attractions = load_curated_attractions()
    selected = [
        item for item in DISTRICTS if districts is None or item[0].lower() in {d.lower() for d in districts}
    ]
    candidates: list[dict[str, Any]] = []
    raw_counts: dict[str, int] = {}
    fetch_errors: dict[str, str] = {}

    for index, (district, province, relation_id) in enumerate(selected, 1):
        try:
            payload = load_raw_or_fetch(
                district=district,
                relation_id=relation_id,
                sleep_seconds=sleep_seconds,
                refresh=refresh,
            )
        except Exception as exc:
            fetch_errors[district] = str(exc)
            raw_counts[district] = 0
            print(f"[{index}/{len(selected)}] {district}: fetch_failed={exc}", flush=True)
            continue
        elements = payload.get("elements", [])
        raw_counts[district] = len(elements)
        district_candidates = [
            build_candidate(
                element=element,
                district=district,
                province=province,
                curated_attractions=curated_attractions,
            )
            for element in elements
        ]
        district_candidates = dedupe_osm_candidates(district_candidates)
        if limit_per_district is not None:
            district_candidates = sorted(
                district_candidates,
                key=lambda item: (
                    item.get("review_status") == "rejected",
                    item.get("duplicate_status") != "strong_new_candidate",
                    -int(item.get("osm_quality_score", 0)),
                ),
            )[:limit_per_district]
        candidates.extend(district_candidates)
        print(
            f"[{index}/{len(selected)}] {district}: raw={len(elements)} candidates={len(district_candidates)}",
            flush=True,
        )

    write_outputs(candidates, raw_counts=raw_counts, fetch_errors=fetch_errors)
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build OSM attraction candidates in the same shape as sri_lanka_attractions.json."
    )
    parser.add_argument("--district", action="append", help="Limit to one district. Can be repeated.")
    parser.add_argument("--refresh", action="store_true", help="Refresh Overpass raw caches.")
    parser.add_argument("--sleep", type=float, default=2.0, help="Delay between Overpass requests.")
    parser.add_argument(
        "--limit-per-district",
        type=int,
        default=None,
        help="Keep only the top N candidates per district after scoring. Useful for smoke tests.",
    )
    args = parser.parse_args()
    candidates = build_candidates(
        districts=args.district,
        refresh=args.refresh,
        sleep_seconds=args.sleep,
        limit_per_district=args.limit_per_district,
    )
    print(f"Wrote {len(candidates)} candidates to {CANDIDATES_JSON}")
    print(f"Wrote review CSV to {REVIEW_CSV}")


if __name__ == "__main__":
    main()
