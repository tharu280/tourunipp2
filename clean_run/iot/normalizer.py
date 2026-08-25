"""Translate the ESP32's telemetry JSON into the shape the mobile app reads.

The firmware and the mobile app were written against separate plan documents and
their payloads never matched. Rather than reflash the hub or rewrite five
screens, the backend owns the translation — it is the one place that already
sits between them, and it is the only one of the three that can be redeployed
without physical access to a vehicle.

Nine differences are reconciled here (see iot-connection-gap-analysis.md §6):

    firmware                          mobile (SafetyDataLive)
    ------------------------------    ----------------------------
    vehicle.riskScore   0-100     ->  riskScore    0.0-1.0, top level
    (absent)                      ->  alertTier    0-3
    driver.eyeStatus     int      ->  'open' | 'closed' | 'unknown'
    driver.yawningStatus int      ->  'normal' | 'yawning'
    vehicle.distance_cm           ->  vehicle.distanceCm
    (absent)                      ->  vehicle.ttcSeconds   (derived)
    gps.speed_kmh                 ->  gps.speedKmh
    timestamp_ms = millis()       ->  timestampMs  (server epoch — see below)
    (absent)                      ->  sequenceNum, driver.earScore

The timestamp one is the subtle one. The firmware sends millis(), i.e. uptime
since boot, but the app feeds that field straight into `new Date(...)` when it
logs an alert — so every alert would timestamp to January 1970. The device has
no RTC and no NTP over the cellular link, so the server's clock is the only
trustworthy source. We overwrite it and keep the device's own value alongside as
`deviceUptimeMs`, which is genuinely useful for spotting a hub that keeps
rebooting.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ── Alert tiers ───────────────────────────────────────────────────────────────
# These MUST stay identical to computeAlertTier() in the mobile app's
# src/types/iot.ts. The device drives buzzer/vibration off its own thresholds and
# the app drives voice prompts off these; if they drift, the driver hears a
# spoken warning that the hardware never gave, or vice versa.
#
# Each entry is (min_risk_score, min_drowsy_level) -> tier, highest first.
_TIER_THRESHOLDS: tuple[tuple[float, int, int], ...] = (
    (0.85, 4, 3),
    (0.70, 3, 2),
    (0.50, 2, 1),
)

# JSON has no Infinity. When the vehicle is stationary the time-to-collision is
# unbounded, so it is capped at a value no dashboard will mistake for a real
# reading.
_TTC_UNBOUNDED_S = 999.0

# Below this the speed reading is noise from a stationary GPS fix, not motion.
_MIN_SPEED_KMH_FOR_TTC = 1.0


def compute_alert_tier(risk_score: float, drowsy_level: int) -> int:
    """Mirror of computeAlertTier() in the mobile app. risk_score is 0.0-1.0."""
    for min_risk, min_drowsy, tier in _TIER_THRESHOLDS:
        if risk_score >= min_risk or drowsy_level >= min_drowsy:
            return tier
    return 0


def _time_to_collision_s(distance_cm: float, speed_kmh: float) -> float:
    """Seconds until impact at the current closing speed.

    Treats the ultrasonic reading as the gap to the object ahead and the GPS
    speed as the closing speed — an overestimate of danger when the object ahead
    is also moving, which is the right way to be wrong for a safety warning.
    """
    if speed_kmh < _MIN_SPEED_KMH_FOR_TTC:
        return _TTC_UNBOUNDED_S
    speed_ms = speed_kmh / 3.6
    return round(min((distance_cm / 100.0) / speed_ms, _TTC_UNBOUNDED_S), 2)


def normalize_telemetry(
    raw: dict[str, Any],
    *,
    sequence_num: int,
    received_at: datetime | None = None,
) -> dict[str, Any]:
    """Firmware telemetry JSON -> the SafetyDataLive document the app listens to.

    `sequence_num` comes from an atomic counter on the device record so the app
    can spot dropped or reordered writes. `received_at` defaults to now and is
    injectable so tests can assert on a fixed timestamp.
    """
    received_at = received_at or datetime.now(timezone.utc)

    driver = raw.get("driver") or {}
    vehicle = raw.get("vehicle") or {}
    gps = raw.get("gps") or {}

    # The camera zeroes every field when the AI server rejects a frame, so a
    # drowsyLevel of 0 means "alert driver" or "no reading at all" depending on
    # this flag alone. Reporting 'unknown' keeps those two apart on the
    # dashboard instead of showing a reassuring "eyes open" for a driver nobody
    # can see.
    driver_visible = bool(driver.get("driverVisible", False)) and bool(
        driver.get("faceValid", 0)
    )

    drowsy_level = int(driver.get("drowsyLevel", 0) or 0)
    # Firmware scores 0-100; the app's gauge and thresholds are 0.0-1.0.
    risk_score = round(min(max(float(vehicle.get("riskScore", 0) or 0), 0.0), 100.0) / 100.0, 4)
    distance_cm = float(vehicle.get("distance_cm", 0) or 0)
    speed_kmh = float(gps.get("speed_kmh", 0) or 0)

    if driver_visible:
        eye_status = "closed" if int(driver.get("eyeStatus", 0) or 0) else "open"
        yawning_status = "yawning" if int(driver.get("yawningStatus", 0) or 0) else "normal"
    else:
        eye_status = "unknown"
        yawning_status = "normal"

    return {
        "riskScore": risk_score,
        "alertTier": compute_alert_tier(risk_score, drowsy_level),
        "driver": {
            "drowsyLevel": drowsy_level,
            "confidence": round(float(driver.get("confidence", 0) or 0), 4),
            "eyeStatus": eye_status,
            "yawningStatus": yawning_status,
            # The eye-aspect-ratio never leaves the AI server — it is not in the
            # 24-byte ESP-NOW struct, and widening that struct would mean
            # reflashing both boards in lockstep. Reported as 0 and typed
            # optional on the app side.
            "earScore": 0.0,
            "driverVisible": driver_visible,
        },
        "vehicle": {
            "distanceCm": distance_cm,
            "ttcSeconds": _time_to_collision_s(distance_cm, speed_kmh),
        },
        "gps": {
            "latitude": float(gps.get("latitude", 0) or 0),
            "longitude": float(gps.get("longitude", 0) or 0),
            "speedKmh": speed_kmh,
            "satellites": int(gps.get("satellites", 0) or 0),
            "fixed": bool(gps.get("fixed", False)),
        },
        # Server clock, not the device's millis() — see the module docstring.
        "timestampMs": int(received_at.timestamp() * 1000),
        "deviceUptimeMs": int(raw.get("timestamp_ms", 0) or 0),
        "sequenceNum": sequence_num,
    }
