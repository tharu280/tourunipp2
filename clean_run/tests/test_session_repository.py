from __future__ import annotations

import unittest

from clean_run.storage.session_repository import SessionRepository


class FakeUpdateResult:
    matched_count = 1


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.index_calls: list[tuple[str, dict]] = []

    def create_index(self, key: str, **kwargs):
        self.index_calls.append((key, kwargs))
        return key

    def find_one(self, query: dict):
        return self.documents.get(query.get("session_id"))

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        session_id = query.get("session_id")
        existing = self.documents.get(session_id, {})
        existing.update(update["$set"])
        self.documents[session_id] = existing
        return FakeUpdateResult()


class SessionRepositoryTests(unittest.TestCase):
    def test_save_planned_session_creates_indexes_and_document(self) -> None:
        collection = FakeCollection()
        repository = SessionRepository(collection)

        session_id = repository.save_planned_session(
            session_id="session-123",
            trip_requirements={"origin": "Colombo", "destination": "Kandy"},
            chat_history=[{"role": "user", "content": "hi"}],
            plan={"route_data": {"route_id": "route_1"}, "crowd_signals": {"risk_level": "low"}},
        )

        self.assertEqual(session_id, "session-123")
        self.assertEqual(len(collection.index_calls), 6)
        saved = collection.documents["session-123"]
        self.assertEqual(saved["trip_requirements"]["destination"], "Kandy")
        self.assertEqual(saved["plan"]["route_data"]["route_id"], "route_1")
        self.assertIn("future_advice", saved)
        self.assertIn("dashboard_cache", saved)

    def test_assign_session_owner_links_saved_plan_to_user(self) -> None:
        collection = FakeCollection()
        repository = SessionRepository(collection)
        repository.save_planned_session(
            session_id="session-owned",
            trip_requirements={"origin": "Colombo", "destination": "Kandy"},
            chat_history=[],
            plan={"route_data": {}},
        )

        assigned = repository.assign_session_owner(
            session_id="session-owned",
            user_id="user-123",
        )

        self.assertTrue(assigned)
        self.assertEqual(collection.documents["session-owned"]["user_id"], "user-123")

    def test_save_planned_session_preserves_created_at_on_update(self) -> None:
        collection = FakeCollection()
        repository = SessionRepository(collection)
        first_session_id = repository.save_planned_session(
            session_id="session-456",
            trip_requirements={"origin": "Colombo"},
            chat_history=[],
            plan={"route_data": {}},
        )
        first_created_at = collection.documents[first_session_id]["created_at"]

        repository.save_planned_session(
            session_id="session-456",
            trip_requirements={"origin": "Colombo", "destination": "Ella"},
            chat_history=[],
            plan={"route_data": {"route_id": "route_2"}},
        )

        saved = collection.documents["session-456"]
        self.assertEqual(saved["created_at"], first_created_at)
        self.assertEqual(saved["trip_requirements"]["destination"], "Ella")
        self.assertEqual(saved["plan"]["route_data"]["route_id"], "route_2")

    def test_add_emotion_checkin_appends_without_raw_image_storage(self) -> None:
        collection = FakeCollection()
        repository = SessionRepository(collection)
        repository.save_planned_session(
            session_id="session-emotion",
            trip_requirements={"origin": "Colombo", "destination": "Kandy"},
            chat_history=[],
            plan={"route_data": {}},
        )

        saved = repository.add_emotion_checkin(
            session_id="session-emotion",
            checkin={
                "emotion_label": "happy",
                "emotion_confidence": 0.8,
                "raw_image_stored": False,
            },
            recommendation={"risk_level": "low"},
        )

        self.assertTrue(saved)
        document = collection.documents["session-emotion"]
        self.assertEqual(len(document["emotion_checkins"]), 1)
        self.assertFalse(document["emotion_summary"]["raw_images_stored"])
        self.assertEqual(document["emotion_summary"]["latest_recommendation"]["risk_level"], "low")


if __name__ == "__main__":
    unittest.main()
