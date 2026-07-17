from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any


class SessionRepository:
    def __init__(self, collection: Any) -> None:
        self.collection = collection
        self._indexes_ensured = False

    def ensure_indexes(self) -> None:
        if self._indexes_ensured:
            return
        self.collection.create_index("session_id", unique=True)
        self.collection.create_index("created_at")
        self.collection.create_index("updated_at")
        self.collection.create_index("user_id")
        self.collection.create_index("trip_requirements.destination")
        self.collection.create_index("trip_requirements.flight_departure_date")
        self.collection.create_index([("status", 1), ("user_id", 1), ("plan.trip_dates", 1)])
        self._indexes_ensured = True

    def save_planned_session(
        self,
        *,
        session_id: str | None,
        trip_requirements: dict[str, Any],
        chat_history: list[dict[str, Any]],
        plan: dict[str, Any],
        future_advice: dict[str, Any] | None = None,
        status: str = "planned",
    ) -> str:
        self.ensure_indexes()
        effective_session_id = session_id or str(uuid.uuid4())
        existing = self.collection.find_one({"session_id": effective_session_id}) or {}
        created_at = existing.get("created_at") or datetime.now(timezone.utc).isoformat()
        updated_at = datetime.now(timezone.utc).isoformat()

        document = {
            "session_id": effective_session_id,
            "status": status,
            "created_at": created_at,
            "updated_at": updated_at,
            "trip_requirements": trip_requirements,
            "chat_session": {
                "history": chat_history,
            },
            "plan": plan,
            "future_advice": future_advice
            or {
                "likely_pressure_tomorrow": None,
                "likely_bottleneck": None,
                "best_timing_adjustment": None,
                "best_fallback_attraction": None,
                "confidence_level": None,
            },
            "dashboard_cache": {
                "location_heatmap_points": [],
                "time_heatmap_cells": [],
            },
            "emotion_checkins": existing.get("emotion_checkins") or [],
            "emotion_summary": existing.get("emotion_summary") or {},
            "condition_notifications": existing.get("condition_notifications") or [],
        }

        self.collection.update_one(
            {"session_id": effective_session_id},
            {"$set": document},
            upsert=True,
        )
        return effective_session_id

    def assign_session_owner(self, *, session_id: str, user_id: str) -> bool:
        self.ensure_indexes()
        result = self.collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "user_id": user_id,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=False,
        )
        return bool(getattr(result, "matched_count", 0))

    def add_condition_notifications(
        self,
        *,
        session_id: str,
        notifications: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Append unseen condition events and keep a bounded session history."""
        self.ensure_indexes()
        existing = self.collection.find_one({"session_id": session_id})
        if existing is None:
            return []

        stored = list(existing.get("condition_notifications") or [])
        known_keys = {
            item.get("dedupe_key")
            for item in stored
            if isinstance(item, dict) and item.get("dedupe_key")
        }
        created: list[dict[str, Any]] = []
        for item in notifications:
            event = dict(item)
            dedupe_key = event.get("dedupe_key")
            if dedupe_key and dedupe_key in known_keys:
                continue
            event["notification_id"] = event.get("notification_id") or str(uuid.uuid4())
            event["read"] = bool(event.get("read", False))
            stored.append(event)
            created.append(event)
            if dedupe_key:
                known_keys.add(dedupe_key)

        if not created:
            return []

        self.collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "condition_notifications": stored[-100:],
                }
            },
            upsert=False,
        )
        return created

    def get_condition_notifications(
        self,
        *,
        session_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]] | None:
        document = self.collection.find_one({"session_id": session_id})
        if document is None:
            return None
        notifications = [
            dict(item)
            for item in document.get("condition_notifications") or []
            if isinstance(item, dict) and (not unread_only or not item.get("read"))
        ]
        notifications.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return notifications[: max(1, min(int(limit), 100))]

    def mark_condition_notification_read(
        self,
        *,
        session_id: str,
        notification_id: str,
    ) -> bool:
        self.ensure_indexes()
        document = self.collection.find_one({"session_id": session_id})
        if document is None:
            return False
        notifications = list(document.get("condition_notifications") or [])
        matched = False
        for item in notifications:
            if isinstance(item, dict) and item.get("notification_id") == notification_id:
                item["read"] = True
                item["read_at"] = datetime.now(timezone.utc).isoformat()
                matched = True
                break
        if not matched:
            return False
        self.collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "condition_notifications": notifications,
                }
            },
            upsert=False,
        )
        return True

    def mark_all_condition_notifications_read(self, *, session_id: str) -> int | None:
        self.ensure_indexes()
        document = self.collection.find_one({"session_id": session_id})
        if document is None:
            return None
        notifications = list(document.get("condition_notifications") or [])
        read_at = datetime.now(timezone.utc).isoformat()
        changed = 0
        for item in notifications:
            if isinstance(item, dict) and not item.get("read"):
                item["read"] = True
                item["read_at"] = read_at
                changed += 1
        if changed:
            self.collection.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "updated_at": read_at,
                        "condition_notifications": notifications,
                    }
                },
                upsert=False,
            )
        return changed

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self.collection.find_one({"session_id": session_id})

    def get_latest_session_for_user(self, user_id: str) -> dict[str, Any] | None:
        self.ensure_indexes()
        return self.collection.find_one(
            {"user_id": user_id},
            sort=[("updated_at", -1)],
        )

    def list_scheduled_sessions(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return bounded, user-owned trip candidates for scheduler-side filtering."""
        self.ensure_indexes()
        cursor = self.collection.find(
            {
                "status": {"$in": sorted(["planned", "refreshed", "active"])},
                "user_id": {"$exists": True, "$ne": None},
                "plan.trip_dates": {"$exists": True, "$ne": []},
            }
        )
        cursor = cursor.sort("updated_at", -1).limit(max(1, min(int(limit), 500)))
        return list(cursor)

    def update_session_intelligence(
        self,
        *,
        session_id: str,
        plan_updates: dict[str, Any],
        future_advice: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> bool:
        self.ensure_indexes()
        updated_at = datetime.now(timezone.utc).isoformat()
        update_doc: dict[str, Any] = {
            "updated_at": updated_at,
        }
        for key, value in plan_updates.items():
            update_doc[f"plan.{key}"] = value
        if future_advice is not None:
            update_doc["future_advice"] = future_advice
        if status is not None:
            update_doc["status"] = status

        result = self.collection.update_one(
            {"session_id": session_id},
            {"$set": update_doc},
            upsert=False,
        )
        return bool(getattr(result, "matched_count", 0))

    def add_emotion_checkin(
        self,
        *,
        session_id: str,
        checkin: dict[str, Any],
        recommendation: dict[str, Any],
        emotion_summary: dict[str, Any] | None = None,
    ) -> bool:
        self.ensure_indexes()
        updated_at = datetime.now(timezone.utc).isoformat()
        existing = self.collection.find_one({"session_id": session_id})
        if existing is None:
            return False

        effective_checkin = dict(checkin)
        effective_checkin["checkin_id"] = effective_checkin.get("checkin_id") or str(uuid.uuid4())
        effective_checkin["recommendation"] = recommendation

        emotion_checkins = list(existing.get("emotion_checkins") or [])
        emotion_checkins.append(effective_checkin)

        default_emotion_summary = {
            "latest": effective_checkin,
            "count": len(emotion_checkins),
            "latest_recommendation": recommendation,
            "raw_images_stored": False,
        }

        result = self.collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "updated_at": updated_at,
                    "emotion_checkins": emotion_checkins,
                    "emotion_summary": emotion_summary or default_emotion_summary,
                }
            },
            upsert=False,
        )
        return bool(getattr(result, "matched_count", 0))
