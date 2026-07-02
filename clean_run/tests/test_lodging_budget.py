from __future__ import annotations

import unittest

from clean_run.enrich.places_engine import score_lodging_place


class LodgingBudgetScoringTests(unittest.TestCase):
    def test_prefers_stronger_in_budget_option_over_very_cheap_one(self) -> None:
        budget = 150000.0
        cheap = {
            "distance_from_anchor_m": 500.0,
            "estimated_nightly_cost_lkr": 5000.0,
        }
        near_budget = {
            "distance_from_anchor_m": 500.0,
            "estimated_nightly_cost_lkr": 120000.0,
        }
        self.assertGreater(
            score_lodging_place(near_budget, lodging_budget_lkr=budget),
            score_lodging_place(cheap, lodging_budget_lkr=budget),
        )

    def test_prefers_good_in_budget_option_over_far_over_budget_one(self) -> None:
        budget = 150000.0
        good_fit = {
            "distance_from_anchor_m": 1200.0,
            "estimated_nightly_cost_lkr": 130000.0,
        }
        over_budget = {
            "distance_from_anchor_m": 1200.0,
            "estimated_nightly_cost_lkr": 260000.0,
        }
        self.assertGreater(
            score_lodging_place(good_fit, lodging_budget_lkr=budget),
            score_lodging_place(over_budget, lodging_budget_lkr=budget),
        )

    def test_penalizes_extremely_cheap_stay_more_than_midrange_budget_stay(self) -> None:
        budget = 150000.0
        ultra_cheap = {
            "distance_from_anchor_m": 500.0,
            "estimated_nightly_cost_lkr": 4500.0,
        }
        midrange = {
            "distance_from_anchor_m": 500.0,
            "estimated_nightly_cost_lkr": 22000.0,
        }
        self.assertGreater(
            score_lodging_place(midrange, lodging_budget_lkr=budget),
            score_lodging_place(ultra_cheap, lodging_budget_lkr=budget),
        )


if __name__ == "__main__":
    unittest.main()
