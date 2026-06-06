# Sri Lanka Curated Accommodations Dataset

This folder contains a broad but still curated Sri Lanka accommodation dataset for route-based and multi-day itinerary planning.

The goal is to reduce dependence on live hotel/place APIs while still keeping the inventory useful, geographically broad, and practical for overnight-stop recommendations.

## Files

- `sri_lanka_accommodations.json`: Main district-grouped accommodation dataset.
- `build_sri_lanka_accommodations.py`: Source-of-truth builder and validator.
- `accommodations_summary.md`: Coverage summary with district, type, price-band, and corridor counts.

## Current Shape

This version is intentionally broader than the attractions dataset, but still curated rather than exhaustive.

- It favors nationally important tourism corridors and real overnight hubs.
- It includes a mix of luxury, premium, mid-range, and budget inventory.
- It avoids turning into a generic scrape of every lodging listing.
- It is especially strong where itinerary planners most often need overnight recommendations:
  - Colombo and the airport gateway
  - southwest coast
  - cultural triangle
  - hill country
  - Yala / south
  - east coast
  - Jaffna corridor

## Schema

Each accommodation record includes:

- `id`
- `name`
- `district`
- `province`
- `latitude`
- `longitude`
- `accommodation_type`
- `price_band`
- `rating_band`
- `tags`
- `ideal_for`
- `summary`
- `source_urls`
- `nearby_area`
- `corridor`
- `notable_location_context`

## Field Notes

- `price_band`: One of `budget`, `midrange`, `premium`, `luxury`.
- `rating_band`: Heuristic quality band: `basic`, `good`, `very_good`, `excellent`.
- `tags`: Lightweight routing and traveler-fit hints such as `beachfront`, `wildlife_access`, `city_stay`, or `surf_access`.
- `ideal_for`: Traveler-fit grouping such as `family`, `couples`, `backpackers`, or `wildlife_lovers`.
- `nearby_area`: Useful local anchor for routing and overnight matching.
- `corridor`: High-level travel corridor the stay most naturally belongs to.

## Coordinate Strategy

Coordinates are stored for every accommodation, but they should be treated as **planning coordinates** rather than exact booking-grade geocodes.

- For many major properties, the location is close to the recognized property zone.
- For some accommodations, especially where exact property-level verification was less practical, the coordinate is the nearby tourism area or accommodation-cluster anchor.
- This is intentional for route planning, where district, corridor, and overnight proximity are more important than front-gate precision.

## Source Strategy

`source_urls` are included for every record, but they are best understood as **research anchors** rather than full booking metadata.

Priority was given to:

- official hotel or brand sites where practical
- Sri Lanka tourism references
- high-recognition property/area references
- area-level verification pages where the property is strongly associated with a known tourism cluster

Because this dataset is for itinerary planning rather than direct reservation handling, source links are used primarily to support accommodation relevance, area fit, and discoverability.

## Curation Strategy

This dataset is not an exhaustive lodging directory.

It intentionally prefers:

- well-known or repeatedly surfaced tourism properties
- accommodations with clear route-planning usefulness
- properties in major overnight corridors
- a balanced mix of high-end, mainstream, and budget-useful stays

It intentionally avoids:

- dumping every small map listing
- obvious duplicates
- low-signal lodging inventory with little tourism relevance

## Validation

Run:

```bash
python3 data/build_sri_lanka_accommodations.py
```

The builder validates:

- required fields
- ID uniqueness
- district/province consistency
- accommodation type validity
- price band validity
- rating band validity
- tag validity
- `ideal_for` validity
- source presence

The same script regenerates:

- `data/sri_lanka_accommodations.json`
- `data/accommodations_summary.md`

## Important Caveat

The user requested a very broad 400-700 accommodation inventory. This version deliberately stops short of a low-quality scrape and instead provides a curated nationwide foundation that is broader than the attractions dataset while staying route-useful.

If needed, this can be expanded further in future passes by deepening specific corridor inventories such as:

- southwest coast
- Ella / hill country
- cultural triangle
- east coast
- safari belts
