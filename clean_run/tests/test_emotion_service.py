from __future__ import annotations

import unittest

from clean_run.emotion.service import (
    attach_location_context,
    build_emotion_checkin_targets,
    build_emotion_recommendation,
    build_emotion_summary,
    build_start_of_day_mood_recommendation,
    sanitize_emotion_checkin,
)


def _sample_session() -> dict:
    return {
        "session_id": "session-emotion",
        "plan": {
            "road_alerts": {"risk_level": "medium", "critical_count": 0, "total_deduplicated": 2},
            "crowd_signals": {"risk_level": "medium", "signal_score": 48},
            "recommended_route": {
                "segments": [
                    {
                        "day": 1,
                        "day_label": "Day 1",
                        "segment_duration_seconds": 5400,
                        "segment_distance_km": 75.0,
                        "weather": {"risk": {"risk_level": "medium", "risk_score": 42}},
                        "selected_attractions": [
                            {
                                "place_id": "temple-tooth",
                                "display_name": "Temple of the Sacred Tooth Relic",
                                "lat": 7.2936,
                                "lng": 80.6413,
                            }
                        ],
                    },
                    {
                        "day": 2,
                        "day_label": "Day 2",
                        "segment_duration_seconds": 12600,
                        "segment_distance_km": 130.0,
                        "weather": {"risk": {"risk_level": "high", "risk_score": 70}},
                        "selected_attractions": [
                            {
                                "place_id": "ambuluwawa",
                                "display_name": "Ambuluwawa Tower",
                                "lat": 7.1618,
                                "lng": 80.5497,
                            }
                        ],
                    }
                ]
            },
        },
    }


class EmotionServiceTests(unittest.TestCase):
    def test_sanitize_checkin_keeps_only_structured_metadata(self) -> None:
        checkin = sanitize_emotion_checkin(
            {
                "attraction_name": "Temple of the Sacred Tooth Relic",
                "emotion_label": "Sad",
                "emotion_confidence": 0.9,
                "image_base64": "should-not-survive",
                "top_predictions": [
                    {"class_name": "sad", "probability": 0.9},
                    {"class_name": "neutral", "probability": 0.1},
                ],
            }
        )

        self.assertEqual(checkin["emotion_label"], "sad")
        self.assertEqual(checkin["emotion_confidence"], 0.9)
        self.assertFalse(checkin["raw_image_stored"])
        self.assertNotIn("image_base64", checkin)

    def test_recommendation_combines_emotion_crowd_weather_and_fatigue(self) -> None:
        checkin = sanitize_emotion_checkin(
            {
                "attraction_name": "Temple of the Sacred Tooth Relic",
                "emotion_label": "sad",
                "emotion_confidence": 0.9,
                "top_predictions": [{"class_name": "sad", "probability": 0.9}],
            }
        )

        recommendation = build_emotion_recommendation(
            checkin=checkin,
            session_document=_sample_session(),
        )

        self.assertEqual(recommendation["current_emotion"], "sad")
        self.assertIn(recommendation["risk_level"], {"medium", "high"})
        self.assertIn("emotion", recommendation["components"])
        self.assertIn("crowd", recommendation["components"])
        self.assertIn("weather", recommendation["components"])
        self.assertFalse(recommendation["privacy"]["raw_image_stored"])

    def test_emotion_targets_expose_planned_attraction_coordinates(self) -> None:
        targets = build_emotion_checkin_targets(_sample_session())

        self.assertEqual(targets["target_count"], 2)
        target = targets["targets"][0]
        self.assertEqual(target["attraction_id"], "temple-tooth")
        self.assertEqual(target["latitude"], 7.2936)
        self.assertTrue(targets["mobile_flow"]["geofence_on_device"])

    def test_location_context_matches_nearby_planned_attraction(self) -> None:
        checkin = sanitize_emotion_checkin(
            {
                "attraction_id": "temple-tooth",
                "emotion_label": "happy",
                "emotion_confidence": 0.88,
                "user_location": {"latitude": 7.2937, "longitude": 80.6414},
            }
        )

        enriched = attach_location_context(
            checkin=checkin,
            session_document=_sample_session(),
        )

        self.assertEqual(enriched["planned_attraction"]["attraction_name"], "Temple of the Sacred Tooth Relic")
        self.assertTrue(enriched["location_context"]["matched_planned_attraction"])
        self.assertTrue(enriched["location_context"]["within_checkin_radius"])

    def test_emotion_summary_tracks_recovery(self) -> None:
        summary = build_emotion_summary(
            checkins=[
                {"emotion_label": "sad", "emotion_confidence": 0.8, "attraction_name": "Crowded Stop"},
                {"emotion_label": "happy", "emotion_confidence": 0.85, "attraction_name": "Garden Stop"},
            ],
            latest_recommendation={"risk_level": "low"},
        )

        self.assertEqual(summary["trend"], "improving")
        self.assertEqual(summary["recovery_status"], "recovered")
        self.assertEqual(summary["latest_recommendation"]["risk_level"], "low")

    def test_start_of_day_mood_recommendation_uses_requested_day_context(self) -> None:
        checkin = sanitize_emotion_checkin(
            {
                "checkin_type": "start_of_day",
                "day": 2,
                "emotion_label": "neutral",
                "emotion_confidence": 0.76,
            }
        )

        recommendation = build_start_of_day_mood_recommendation(
            checkin=checkin,
            session_document=_sample_session(),
        )

        self.assertEqual(recommendation["type"], "start_of_day")
        self.assertEqual(recommendation["day"], 2)
        self.assertEqual(recommendation["day_label"], "Day 2")
        self.assertEqual(recommendation["day_context"]["weather_level"], "high")
        self.assertIn("Ambuluwawa Tower", recommendation["day_context"]["attractions"])
        self.assertIn("day ahead", recommendation["day_ahead_prediction"])
        self.assertFalse(recommendation["privacy"]["raw_image_stored"])


if __name__ == "__main__":
    unittest.main()
