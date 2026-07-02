# Accommodation Summary

- Total accommodation count: **1578**
- Districts covered: **25**

## Minimal Record Schema

- `id`
- `name`
- `district`
- `latitude`
- `longitude`
- `estimated_nightly_cost_lkr`

## Accommodation Count by District

- `Puttalam`: 76
- `Colombo`: 75
- `Gampaha`: 75
- `Hambantota`: 75
- `Jaffna`: 75
- `Kalutara`: 75
- `Kandy`: 75
- `Matale`: 75
- `Matara`: 75
- `Monaragala`: 75
- `Ratnapura`: 75
- `Trincomalee`: 75
- `Galle`: 74
- `Kegalle`: 74
- `Nuwara Eliya`: 74
- `Polonnaruwa`: 74
- `Ampara`: 73
- `Anuradhapura`: 73
- `Badulla`: 73
- `Batticaloa`: 72
- `Kurunegala`: 54
- `Mannar`: 16
- `Kilinochchi`: 9
- `Vavuniya`: 6
- `Mullaitivu`: 5

## Maintenance Notes

- This dataset is intentionally minimal so nightly costs can be filled and maintained by hand.
- Ranking logic uses only `estimated_nightly_cost_lkr` and distance from the overnight anchor.
- `estimated_nightly_cost_lkr` may be an integer or the literal string `unavailable` during manual price review.
- Keep IDs stable once the new dataset is rebuilt from your Booking-based district inputs.
