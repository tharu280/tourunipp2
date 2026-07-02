# Sri Lanka Accommodation Dataset

This dataset is intentionally minimal.

The planner only needs accommodation data for two ranking inputs:

- distance from the overnight anchor
- estimated nightly cost in LKR

Everything else was removed so the file is easier to maintain by hand.

## Files

- `sri_lanka_accommodations.json`: Main accommodation dataset.
- `build_sri_lanka_accommodations.py`: Validator and normalizer for the minimal dataset.
- `accommodations_summary.md`: Simple count summary by district.

## Final Record Schema

Each accommodation record contains only:

- `id`
- `name`
- `district`
- `latitude`
- `longitude`
- `estimated_nightly_cost_lkr`

Example:

```json
{
  "id": "lk_acc_kandy_example_hotel_abc123",
  "name": "Example Hotel",
  "district": "Kandy",
  "latitude": 7.2906,
  "longitude": 80.6337,
  "estimated_nightly_cost_lkr": 25000
}
```

## Structure

The JSON is stored as a flat list:

```json
{
  "metadata": {},
  "accommodations": []
}
```

This keeps manual editing simpler than nested district sections while still preserving the `district` field for filtering and organization.

## Validation

Run:

```bash
python3 data/build_sri_lanka_accommodations.py
```

The builder:

- reads the current dataset
- keeps only the minimal fields
- validates IDs, coordinates, and nightly costs
- rewrites the JSON in normalized order
- regenerates `accommodations_summary.md`

## Ranking Use

Lodging ranking code uses only:

- `estimated_nightly_cost_lkr`
- distance from the day-end or overnight anchor

No accommodation ratings, tags, types, summaries, review counts, or source metadata are required anymore.

## Manual Editing Notes

- Keep IDs stable once they are in use.
- Use real property coordinates.
- Fill `estimated_nightly_cost_lkr` with the value you want the planner to rank against.
- After manual edits, rerun the builder to catch duplicates or invalid values.
