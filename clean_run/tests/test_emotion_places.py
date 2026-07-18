from __future__ import annotations

import unittest
from unittest.mock import patch

from clean_run.emotion.places import (
    build_nearby_emotion_tips,
    build_overpass_query,
    rank_places,
)


class EmotionPlacesTests(unittest.TestCase):
    def test_query_uses_supplied_trip_start_coordinates(self) -> None:
        query = build_overpass_query(
            latitude=6.9271,
            longitude=79.8612,
            emotion="happy",
            hobbies=["Photography"],
        )
        self.assertIn("6.900151", query)
        self.assertNotIn("7.290600", query)
        self.assertIn('"tourism"', query)

    def test_arts_hobby_boosts_a_cultural_place(self) -> None:
        elements = [
            {
                "type": "node",
                "id": 1,
                "lat": 7.291,
                "lon": 80.634,
                "tags": {"name": "Kandy Music Hall", "amenity": "music_venue"},
            },
            {
                "type": "node",
                "id": 2,
                "lat": 7.291,
                "lon": 80.634,
                "tags": {"name": "City View", "tourism": "viewpoint"},
            },
        ]
        places = rank_places(elements, 7.2906, 80.6337, "neutral", ["Arts"])
        self.assertEqual(places[0]["name"], "Kandy Music Hall")
        self.assertEqual(places[0]["hobby_matches"], ["Arts"])
        self.assertEqual(places[0]["activity_type"], "Arts & music")
        self.assertEqual(places[0]["recommendation_label"], "Fresh Pick")
        self.assertTrue(places[0]["top_pick"])
        self.assertIn("Arts", places[0]["why_for_you"])

    def test_selected_food_interest_outranks_generic_happy_attraction(self) -> None:
        elements = [
            {
                "type": "node",
                "id": 10,
                "lat": 6.9275,
                "lon": 79.8615,
                "tags": {"name": "Generic Landmark", "tourism": "attraction"},
            },
            {
                "type": "node",
                "id": 11,
                "lat": 6.9290,
                "lon": 79.8630,
                "tags": {"name": "Local Food House", "amenity": "restaurant"},
            },
        ]

        places = rank_places(elements, 6.9271, 79.8612, "happy", ["Food"])

        self.assertEqual(places[0]["name"], "Local Food House")
        self.assertEqual(places[0]["hobby_matches"], ["Food"])
        self.assertTrue(places[0]["interest_match"])
        self.assertFalse(places[1]["interest_match"])

    def test_nearby_tips_use_session_origin_and_do_not_persist_places(self) -> None:
        session = {
            "plan": {
                "origin_resolved": {
                    "name": "Colombo",
                    "lat": 6.9271,
                    "lng": 79.8612,
                }
            }
        }
        elements = [
            {
                "type": "node",
                "id": 5,
                "lat": 6.928,
                "lon": 79.862,
                "tags": {"name": "History Museum", "tourism": "museum"},
            }
        ]
        with patch("clean_run.emotion.places.fetch_overpass_places", return_value=elements) as fetch:
            result = build_nearby_emotion_tips(session, "neutral", ["Culture"])

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["location"]["name"], "Colombo")
        self.assertEqual(result["location"]["source"], "trip_start")
        self.assertEqual(result["recommendations"][0]["name"], "History Museum")
        self.assertEqual(result["headline"], "Smart Picks For You")
        self.assertEqual(result["recommendations"][0]["best_time"], "Late morning")
        fetch.assert_called_once_with(6.9271, 79.8612, "neutral", ["Culture"])

    def test_nearby_tips_prefer_selected_checkpoint_coordinates(self) -> None:
        session = {
            "plan": {
                "origin_resolved": {
                    "name": "Colombo",
                    "lat": 6.9271,
                    "lng": 79.8612,
                }
            }
        }
        checkin = {
            "attraction_name": "Temple of the Sacred Tooth Relic",
            "user_location": {"latitude": 7.2936, "longitude": 80.6413},
        }
        with patch("clean_run.emotion.places.fetch_overpass_places", return_value=[]) as fetch:
            result = build_nearby_emotion_tips(
                session,
                "neutral",
                ["Culture"],
                checkin=checkin,
            )

        self.assertEqual(result["location"]["name"], "Temple of the Sacred Tooth Relic")
        self.assertEqual(result["location"]["source"], "emotion_checkin")
        fetch.assert_called_once_with(7.2936, 80.6413, "neutral", ["Culture"])


if __name__ == "__main__":
    unittest.main()
