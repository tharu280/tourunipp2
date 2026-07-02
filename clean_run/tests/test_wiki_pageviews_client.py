from __future__ import annotations

import unittest
from unittest.mock import patch

from clean_run.integrations.wiki_pageviews_client import (
    MonthlyPageviewRow,
    extract_wiki_title,
    get_attraction_monthly_interest,
)


class WikiPageviewsClientTests(unittest.TestCase):
    def test_extract_wiki_title_from_source_urls(self) -> None:
        title = extract_wiki_title(
            [
                "https://www.sltda.gov.lk/en/tourist-attractions",
                "https://en.wikipedia.org/wiki/Nine_Arch_Bridge",
            ]
        )

        self.assertEqual(title, "Nine_Arch_Bridge")

    @patch(
        "clean_run.integrations.wiki_pageviews_client.load_monthly_pageview_cache",
        return_value=(
            MonthlyPageviewRow("sigiriya", "Sigiriya", "Sigiriya", 2025, 1, 1000, "test"),
            MonthlyPageviewRow("sigiriya", "Sigiriya", "Sigiriya", 2025, 7, 9000, "test"),
            MonthlyPageviewRow("sigiriya", "Sigiriya", "Sigiriya", 2025, 12, 12000, "test"),
        ),
    )
    def test_future_month_uses_latest_matching_month_proxy(self, _mock_cache) -> None:
        payload = get_attraction_monthly_interest(
            place={
                "place_id": "sigiriya",
                "display_name": "Sigiriya",
                "source_urls": ["https://en.wikipedia.org/wiki/Sigiriya"],
            },
            iso_date="2026-12-24",
        )

        self.assertEqual(payload["level"], "high")
        self.assertEqual(payload["matched_year"], 2025)
        self.assertEqual(payload["matched_month"], 12)
        self.assertEqual(payload["views"], 12000)
        self.assertTrue(payload["is_seasonal_proxy"])


if __name__ == "__main__":
    unittest.main()
