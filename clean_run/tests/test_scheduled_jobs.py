from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from clean_run.notifications.scheduled_jobs import (
    SchedulerSettings,
    build_mood_checkin_reminder,
    is_condition_refresh_eligible,
    queue_mood_reminders,
    run_condition_refresh_batch,
)


def trip_document(
    session_id: str = "session-1",
    *,
    start: str = "2026-07-20",
    end: str = "2026-07-23",
) -> dict:
    return {
        "session_id": session_id,
        "user_id": "user-1",
        "status": "planned",
        "trip_requirements": {"destination": "Kandy"},
        "plan": {
            "trip_dates": [start, end],
            "daily_briefings": [{"day": 1, "location": "Colombo"}],
        },
        "emotion_checkins": [],
    }


class FakeReminderRepository:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    def add_condition_notifications(self, *, session_id: str, notifications: list[dict]):
        created = []
        for notification in notifications:
            key = notification["dedupe_key"]
            if key in self.keys:
                continue
            self.keys.add(key)
            created.append(notification)
        return created


class ScheduledJobTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = SchedulerSettings(
            timezone_name="Asia/Colombo",
            lookahead_days=7,
            mood_start_hour=8,
            mood_end_hour=20,
        )

    def test_condition_refresh_eligibility_requires_owned_relevant_trip(self) -> None:
        document = trip_document()
        self.assertTrue(
            is_condition_refresh_eligible(document, today=date(2026, 7, 17), lookahead_days=7)
        )
        document["user_id"] = None
        self.assertFalse(
            is_condition_refresh_eligible(document, today=date(2026, 7, 17), lookahead_days=7)
        )

    def test_condition_refresh_skips_expired_and_far_future_trips(self) -> None:
        self.assertFalse(
            is_condition_refresh_eligible(
                trip_document(start="2026-06-01", end="2026-06-04"),
                today=date(2026, 7, 17),
                lookahead_days=7,
            )
        )
        self.assertFalse(
            is_condition_refresh_eligible(
                trip_document(start="2026-08-01", end="2026-08-04"),
                today=date(2026, 7, 17),
                lookahead_days=7,
            )
        )

    def test_mood_reminder_is_active_trip_daytime_only(self) -> None:
        now = datetime(2026, 7, 20, 4, 37, tzinfo=timezone.utc)  # 10:07 in Colombo.
        document = trip_document()
        document["emotion_checkins"] = [{"timestamp": "2026-07-20T02:00:00+00:00"}]
        reminder = build_mood_checkin_reminder(
            document,
            now=now,
            settings=self.settings,
        )
        self.assertIsNotNone(reminder)
        self.assertEqual(reminder["day"], 1)
        self.assertEqual(reminder["push"]["data"]["screen"], "tips")
        self.assertEqual(reminder["type"], "mood_checkin_reminder")

        overnight = datetime(2026, 7, 19, 20, 0, tzinfo=timezone.utc)  # 01:30 in Colombo.
        self.assertIsNone(
            build_mood_checkin_reminder(
                document,
                now=overnight,
                settings=self.settings,
            )
        )

    def test_mood_reminder_waits_for_first_manual_checkin(self) -> None:
        reminder = build_mood_checkin_reminder(
            trip_document(),
            now=datetime(2026, 7, 20, 4, 37, tzinfo=timezone.utc),
            settings=self.settings,
        )
        self.assertIsNone(reminder)

    def test_recent_checkin_suppresses_same_slot_reminder(self) -> None:
        document = trip_document()
        document["emotion_checkins"] = [{"timestamp": "2026-07-20T04:35:00+00:00"}]
        reminder = build_mood_checkin_reminder(
            document,
            now=datetime(2026, 7, 20, 4, 37, tzinfo=timezone.utc),
            settings=self.settings,
        )
        self.assertIsNone(reminder)

    def test_mood_reminders_are_deduplicated_per_two_hour_slot(self) -> None:
        repository = FakeReminderRepository()
        now = datetime(2026, 7, 20, 4, 37, tzinfo=timezone.utc)
        document = trip_document()
        document["emotion_checkins"] = [{"timestamp": "2026-07-20T02:00:00+00:00"}]
        first = queue_mood_reminders(
            repository,
            [document],
            now=now,
            settings=self.settings,
        )
        second = queue_mood_reminders(
            repository,
            [document],
            now=now,
            settings=self.settings,
        )
        self.assertEqual(first["created_count"], 1)
        self.assertEqual(second["created_count"], 0)

    async def test_batch_refresh_continues_after_one_session_fails(self) -> None:
        async def refresh_one(session_id: str):
            if session_id == "broken":
                raise RuntimeError("weather upstream failed")
            return {"condition_updates": [{"type": "condition_change"}], "changed_package": False}

        payload = await run_condition_refresh_batch(
            [trip_document("healthy"), trip_document("broken")],
            refresh_one=refresh_one,
            now=datetime(2026, 7, 20, 4, 37, tzinfo=timezone.utc),
            settings=self.settings,
        )
        self.assertEqual(payload["refreshed_count"], 1)
        self.assertEqual(payload["failed_count"], 1)
        self.assertFalse(payload["results"][0]["changed_package"])


if __name__ == "__main__":
    unittest.main()
