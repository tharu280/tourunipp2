# Sri Lanka Curated Attractions Dataset

This folder contains a curated Sri Lanka tourism dataset built for route-based and day-based itinerary generation.

The goal is not to mirror a generic maps export. Instead, the dataset tries to give an itinerary engine enough meaningful attraction choices per district without flooding it with weak POIs.

## Files

- `sri_lanka_attractions.json`: Main dataset, grouped by district.
- `build_sri_lanka_attractions.py`: Source-of-truth builder and validator for the dataset.
- `dataset_summary.md`: Quick coverage summary with counts by district, counts for the highest-tourism focus districts, and tier totals.

## Intended Use

This dataset is meant to help itinerary logic answer questions like:

- What are the strongest attractions near a route segment?
- If a traveler spends 1-3 days in a district, what are the best attraction options?
- Which attractions are iconic anchors versus secondary or optional stops?
- How can an itinerary mix beaches, viewpoints, temples, wildlife, museums, and scenic stops without falling back to noisy generic POIs?

## Design Approach

This is a **curated expansion**, not exhaustive scraping.

- It includes high-value attractions that tourists would realistically consider.
- It favors tourism-heavy districts and major travel corridors with richer coverage.
- It still includes moderate and sparse districts, but avoids padding them with low-value filler.
- It allows distinct sub-stops inside major heritage areas when they are genuinely itinerary-meaningful.

This means the dataset is intentionally broader than a minimalist shortlist, but still narrower than a raw place index. In its current form it is a mid-sized curated dataset designed to support multi-day routing and stronger district-level option sets without becoming a generic places dump.

## Schema

Top-level structure:

```json
{
  "metadata": {},
  "districts": [
    {
      "district": "Kandy",
      "province": "Central",
      "attraction_count": 8,
      "attractions": [
        {
          "id": "lk_kandy_temple_of_the_sacred_tooth_relic",
          "name": "Temple of the Sacred Tooth Relic",
          "district": "Kandy",
          "province": "Central",
          "categories": ["cultural", "historic", "religious"],
          "latitude": 7.2936,
          "longitude": 80.6413,
          "importance_score": 10,
          "estimated_visit_hours": 2.5,
          "tier": "tier_1",
          "tags": ["iconic", "must_see", "photography", "unesco"],
          "summary": "Short planning-oriented description.",
          "source_urls": ["https://example.org/source1", "https://example.org/source2"]
        }
      ]
    }
  ]
}
```

## Field Notes

- `id`: Deterministic slug built from district and attraction name.
- `categories`: Curated itinerary categories, not a raw POI taxonomy.
- `latitude` / `longitude`: Practical traveler-facing coordinates for matching to routes and day plans. For very large parks, heritage zones, and beaches this is a planning coordinate, not necessarily a geometric center.
- `importance_score`: Heuristic score from 1 to 10 for trip-planning priority.
- `estimated_visit_hours`: Typical planning duration for a standard visit.
- `tier`: High-level itinerary role.
- `tags`: Lightweight planning hints such as `must_see`, `family_friendly`, `couples`, or `day_trip`.
- `summary`: Short tourism-oriented description intended for UI and ranking logic.
- `source_urls`: Research links used for significance and verification.

## Tier Definitions

- `tier_1`: Iconic, nationally significant, or clear must-see attractions.
- `tier_2`: Strong supporting attractions that meaningfully improve real itineraries.
- `tier_3`: Useful optional local attractions that are still meaningful, but less essential.

## Importance Score Rubric

- `10`: Nationally iconic, internationally famous, or exceptionally high-value attractions.
- `8-9`: Major itinerary anchors with broad tourism relevance.
- `6-7`: Strong supporting attractions worth deliberate inclusion.
- `4-5`: Conservative optional attractions kept only when still useful for itinerary generation.
- `1-3`: Avoided unless there is a compelling reason.

## District Coverage Strategy

- Major tourism districts are given several options so route segments passing through them can produce varied itineraries.
- The strongest tourism districts can carry deeper `tier_2` and `tier_3` coverage when those additions remain genuinely useful for itinerary generation.
- Major corridors such as the south coast, hill country, cultural triangle, east coast, and northern peninsula are expanded deliberately so route planning has realistic stop combinations.
- Moderate districts are given enough coverage to avoid repetitive or underpowered plans.
- A few districts remain intentionally sparse because mainstream tourism inventory is genuinely limited and adding more entries would degrade quality.

The dataset therefore aims for **coverage with judgment**, not equality for its own sake.

## Sources

Primary or high-quality sources were preferred where possible, including:

- Sri Lanka Tourism Development Authority destination pages
- Sri Lanka Tourism Development Authority official attractions listing as a cross-reference validation source
- UNESCO World Heritage Centre pages
- Department of Wildlife Conservation pages
- Department of National Botanic Gardens pages
- Department of National Museums pages
- Other official Sri Lankan government tourism or heritage pages when appropriate

Wikipedia is used mainly as a secondary reference for entity verification, coordinates, and page-level cross-checking.

## SLTDA Cross-Reference Pass

The current version includes a careful improvement pass against the official SLTDA attractions listing at [sltda.gov.lk/en/tourist-attractions](https://www.sltda.gov.lk/en/tourist-attractions).

SLTDA was used to:

- confirm that many existing attractions and destination anchors are officially tourism-relevant
- strengthen source support for well-known attractions already in the dataset
- identify a small number of meaningful gaps where official tourism coverage and itinerary value aligned

SLTDA was **not** used as a blind extraction source. When the SLTDA listing described a destination area rather than a precise attraction, it was treated as corridor or district validation rather than automatically converted into a new record.

## Research Assumptions

- If a large attraction spans multiple districts, it is assigned to the district that is most practical for itinerary planning or most commonly associated with the visitor experience.
- Some major heritage zones are represented both as a broader site and as distinct sub-attractions when those sub-stops are genuinely useful in day planning.
- Coordinates are conservative planning coordinates, not surveying-grade geodata.

## Validation

Run:

```bash
python3 data/build_sri_lanka_attractions.py
```

The builder validates:

- required fields
- district/province consistency
- tier validity
- ID uniqueness
- category/tag validity
- score range
- positive visit duration
- presence of sources

The same script also regenerates:

- `data/sri_lanka_attractions.json`
- `data/dataset_summary.md`
