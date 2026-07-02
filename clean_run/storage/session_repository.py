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
        self.collection.create_index("trip_requirements.destination")
        self.collection.create_index("trip_requirements.flight_departure_date")
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
        }

        self.collection.update_one(
            {"session_id": effective_session_id},
            {"$set": document},
            upsert=True,
        )
        return effective_session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self.collection.find_one({"session_id": session_id})

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
