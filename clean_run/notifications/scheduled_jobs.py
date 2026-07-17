from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import os
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo


ACTIVE_SESSION_STATUSES = {"planned", "refreshed", "active"}


@dataclass(frozen=True)
class SchedulerSettings:
    timezone_name: str = "Asia/Colombo"
    lookahead_days: int = 7
    mood_start_hour: int = 8
    mood_end_hour: int = 20

    @classmethod
    def from_env(cls) -> "SchedulerSettings":
        return cls(
            timezone_name=os.getenv("SCHEDULER_TIMEZONE", "Asia/Colombo"),
            lookahead_days=max(0, int(os.getenv("SCHEDULER_LOOKAHEAD_DAYS", "7"))),
            mood_start_hour=max(0, min(23, int(os.getenv("MOOD_REMINDER_START_HOUR", "8")))),
            mood_end_hour=max(1, min(24, int(os.getenv("MOOD_REMINDER_END_HOUR", "20")))),
        )


def _trip_dates(document: dict[str, Any]) -> list[date]:
    values = (document.get("plan") or {}).get("trip_dates") or []
    parsed: list[date] = []
    for value in values:
        try:
            parsed.append(date.fromisoformat(str(value)[:10]))
        except (TypeError, ValueError):
            continue
    return sorted(set(parsed))


def trip_window(document: dict[str, Any]) -> tuple[date, date] | None:
    values = _trip_dates(document)
    if not values:
        return None
    return values[0], values[-1]


def is_condition_refresh_eligible(
    document: dict[str, Any],
    *,
    today: date,
    lookahead_days: int = 7,
) -> bool:
    if not document.get("user_id"):
        return False
    if str(document.get("status") or "").lower() not in ACTIVE_SESSION_STATUSES:
        return False
    window = trip_window(document)
    if window is None:
        return False
    start_date, end_date = window
    return end_date >= today and (start_date - today).days <= max(0, lookahead_days)


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _day_number(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_checkin_in_current_slot(
    document: dict[str, Any],
    *,
    slot_start: datetime,
    slot_end: datetime,
) -> bool:
    for checkin in document.get("emotion_checkins") or []:
        if not isinstance(checkin, dict):
            continue
        timestamp = _parse_timestamp(checkin.get("timestamp") or checkin.get("created_at"))
        if timestamp is None:
            continue
        local_timestamp = timestamp.astimezone(slot_start.tzinfo)
        if slot_start <= local_timestamp < slot_end:
            return True
    return False


def _has_completed_mood_checkin(document: dict[str, Any]) -> bool:
    """Scheduled reminders are opt-in only after the user's first check-in."""
    return any(
        isinstance(checkin, dict)
        for checkin in document.get("emotion_checkins") or []
    )


def build_mood_checkin_reminder(
    document: dict[str, Any],
    *,
    now: datetime,
    settings: SchedulerSettings,
) -> dict[str, Any] | None:
    if not document.get("user_id"):
        return None
    if str(document.get("status") or "").lower() not in ACTIVE_SESSION_STATUSES:
        return None
    window = trip_window(document)
    if window is None:
        return None
    if not _has_completed_mood_checkin(document):
        return None

    local_now = now.astimezone(ZoneInfo(settings.timezone_name))
    start_date, end_date = window
    if not start_date <= local_now.date() <= end_date:
        return None
    if not settings.mood_start_hour <= local_now.hour < settings.mood_end_hour:
        return None

    slot_hour = (local_now.hour // 2) * 2
    slot_start = datetime.combine(
        local_now.date(),
        time(hour=slot_hour),
        tzinfo=local_now.tzinfo,
    )
    slot_end = slot_start + timedelta(hours=2)
    if _has_checkin_in_current_slot(document, slot_start=slot_start, slot_end=slot_end):
        return None

    day_number = (local_now.date() - start_date).days + 1
    briefings = (document.get("plan") or {}).get("daily_briefings") or []
    briefing = next(
        (
            item
            for item in briefings
            if isinstance(item, dict) and _day_number(item.get("day")) == day_number
        ),
        {},
    )
    place_name = (
        briefing.get("location")
        or briefing.get("area")
        or (document.get("trip_requirements") or {}).get("destination")
        or "today's route"
    )
    session_id = str(document.get("session_id") or "")
    created_at = now.astimezone(timezone.utc).isoformat()
    return {
        "type": "mood_checkin_reminder",
        "category": "emotion",
        "severity": "low",
        "created_at": created_at,
        "dedupe_key": f"mood-checkin:{session_id}:{local_now.date().isoformat()}:{slot_hour:02d}",
        "title": "How are you feeling?",
        "message": f"Day {day_number} near {place_name}: take a quick mood check-in for updated travel tips.",
        "recommendation": {
            "action": "Open Tips and add a photo or choose how you feel.",
            "reason": "Mood check-ins are only evaluated when you choose to submit one.",
        },
        "day": day_number,
        "user_id": document.get("user_id"),
        "push": {
            "eligible": True,
            "title": "TourUni mood check-in",
            "body": f"How are you feeling on Day {day_number}? Refresh your tips when you are ready.",
            "data": {
                "screen": "tips",
                "action": "open_mood_checkin",
                "session_id": session_id,
                "day": day_number,
            },
        },
    }


async def run_condition_refresh_batch(
    documents: list[dict[str, Any]],
    *,
    refresh_one: Callable[[str], Awaitable[dict[str, Any] | None]],
    now: datetime,
    settings: SchedulerSettings,
) -> dict[str, Any]:
    local_today = now.astimezone(ZoneInfo(settings.timezone_name)).date()
    eligible = [
        document
        for document in documents
        if is_condition_refresh_eligible(
            document,
            today=local_today,
            lookahead_days=settings.lookahead_days,
        )
    ]
    results: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for document in eligible:
        session_id = str(document.get("session_id") or "")
        if not session_id:
            continue
        try:
            payload = await refresh_one(session_id)
            if payload is None:
                failed.append({"session_id": session_id, "error": "Session disappeared during refresh."})
                continue
            results.append(
                {
                    "session_id": session_id,
                    "created_notifications": len(payload.get("condition_updates") or []),
                    "changed_package": bool(payload.get("changed_package", False)),
                }
            )
        except Exception as exc:  # One upstream failure must not stop other trips.
            failed.append({"session_id": session_id, "error": str(exc)[:300]})

    return {
        "job": "refresh_conditions",
        "scanned_count": len(documents),
        "eligible_count": len(eligible),
        "refreshed_count": len(results),
        "failed_count": len(failed),
        "results": results,
        "failures": failed,
        "completed_at": now.astimezone(timezone.utc).isoformat(),
    }


def queue_mood_reminders(
    repository: Any,
    documents: list[dict[str, Any]],
    *,
    now: datetime,
    settings: SchedulerSettings,
) -> dict[str, Any]:
    created: list[dict[str, Any]] = []
    eligible_count = 0
    for document in documents:
        reminder = build_mood_checkin_reminder(document, now=now, settings=settings)
        if reminder is None:
            continue
        eligible_count += 1
        session_id = str(document.get("session_id") or "")
        stored = repository.add_condition_notifications(
            session_id=session_id,
            notifications=[reminder],
        )
        created.extend(stored)

    return {
        "job": "queue_mood_reminders",
        "scanned_count": len(documents),
        "eligible_count": eligible_count,
        "created_count": len(created),
        "notifications": created,
        "completed_at": now.astimezone(timezone.utc).isoformat(),
        "delivery": "in_app_and_push_ready",
    }
