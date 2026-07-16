from __future__ import annotations

from copy import deepcopy
import unittest

from clean_run.notifications.condition_updates import build_condition_update_events


def _plan(
    *,
    rain: int = 20,
    weather: str = "low",
    crowd_score: int = 30,
    crowd: str = "low",
    road_alerts: int = 0,
    roads: str = "low",
) -> dict:
    return {
        "daily_briefings": [
            {
                "day": 1,
                "date": "2026-07-20",
                "location_label": "Galle",
                "weather": {
                    "risk_level": weather,
                    "rain_probability_pct": rain,
                },
                "crowd": {
                    "risk_level": crowd,
                    "score": crowd_score,
                },
                "roads": {
                    "risk_level": roads,
                    "active_alert_count": road_alerts,
                },
                "attractions": [{"id": "galle-fort", "name": "Galle Fort"}],
                "recommendations": ["Visit the sheltered museum first and re-check the fort later."],
            }
        ]
    }


class ConditionUpdateTests(unittest.TestCase):
    def test_combines_meaningful_deterioration_into_one_push_ready_event(self) -> None:
        previous = _plan()
        current = _plan(
            rain=82,
            weather="high",
            crowd_score=68,
            crowd="high",
            road_alerts=2,
            roads="medium",
        )

        events = build_condition_update_events(
            session_id="session-1",
            previous_plan=previous,
            current_plan=current,
            user_id="user-1",
            created_at="2026-07-19T12:00:00+00:00",
        )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["category"], "multi_signal")
        self.assertEqual(event["severity"], "high")
        self.assertEqual([item["signal"] for item in event["changes"]], ["weather", "crowd", "roads"])
        self.assertEqual(event["location_label"], "Galle")
        self.assertEqual(event["attraction"]["name"], "Galle Fort")
        self.assertTrue(event["recommendation"]["alternative_search_recommended"])
        self.assertTrue(event["push"]["eligible"])
        self.assertEqual(event["push"]["data"]["screen"], "trip_updates")

    def test_ignores_small_changes_that_do_not_cross_a_threshold(self) -> None:
        events = build_condition_update_events(
            session_id="session-2",
            previous_plan=_plan(rain=30, crowd_score=32),
            current_plan=_plan(rain=45, crowd_score=39),
        )

        self.assertEqual(events, [])

    def test_does_not_mutate_previous_or_current_plan(self) -> None:
        previous = _plan()
        current = _plan(rain=75, weather="medium")
        previous_copy = deepcopy(previous)
        current_copy = deepcopy(current)

        build_condition_update_events(
            session_id="session-3",
            previous_plan=previous,
            current_plan=current,
        )

        self.assertEqual(previous, previous_copy)
        self.assertEqual(current, current_copy)


if __name__ == "__main__":
    unittest.main()
