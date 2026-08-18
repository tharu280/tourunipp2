"""End-to-end wiring test for POST /iot/telemetry.

Uses the byte-for-byte payload the esp32-main sketch's buildTelemetryJson()
produces, so a firmware field rename that nobody mirrors here fails loudly
instead of silently blanking the dashboard.

Mongo and Firebase are faked — this asserts on the route's contract and its
call sequence, not on storage.
"""
from __future__ import annotations

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from clean_run.api import app

DEVICE_ID = "ESP32-MAC-F42DC9718A60"
DEVICE_SECRET = "test-device-secret"

# Exactly what the firmware sends.
FIRMWARE_PAYLOAD = {
    "device_id": DEVICE_ID,
    "driver": {
        "drowsyLevel": 3,
        "confidence": 0.87,
        "eyeStatus": 1,
        "yawningStatus": 1,
        "faceValid": 1,
        "driverVisible": True,
    },
    "vehicle": {"riskScore": 72, "distance_cm": 85.0},
    "gps": {
        "latitude": 6.9271,
        "longitude": 79.8612,
        "speed_kmh": 54.3,
        "satellites": 9,
        "fixed": True,
    },
    "timestamp_ms": 184523,
}


class TelemetryIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.rtdb = mock.MagicMock()
        # Default: device authenticates, seq 41, was previously at tier 0.
        self.patches = [
            mock.patch("clean_run.iot.iot_router.rtdb_service", self.rtdb),
            mock.patch(
                "clean_run.iot.iot_router.get_device_by_secret",
                return_value={"device_id": DEVICE_ID, "owner_user_id": "u1"},
            ),
            mock.patch(
                "clean_run.iot.iot_router.record_telemetry_tick",
                return_value=(41, 0),
            ),
            mock.patch(
                "clean_run.iot.iot_router.insert_alert_event", return_value="evt-1"
            ),
        ]
        for p in self.patches:
            p.start()
        self.rtdb.should_snapshot.return_value = False

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()

    def _post(self, **kwargs):
        headers = {"X-Device-Id": DEVICE_ID, "X-Device-Secret": DEVICE_SECRET}
        headers.update(kwargs.pop("headers", {}))
        return self.client.post("/iot/telemetry", json=FIRMWARE_PAYLOAD, headers=headers, **kwargs)

    def test_accepts_firmware_payload_and_writes_normalized_live_data(self) -> None:
        response = self._post()

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")  # device parses no body

        self.rtdb.write_live.assert_called_once()
        device_id, live = self.rtdb.write_live.call_args[0]
        self.assertEqual(device_id, DEVICE_ID)
        # The app's schema, not the firmware's.
        self.assertAlmostEqual(live["riskScore"], 0.72)
        self.assertEqual(live["alertTier"], 2)
        self.assertEqual(live["driver"]["eyeStatus"], "closed")
        self.assertEqual(live["vehicle"]["distanceCm"], 85.0)
        self.assertEqual(live["gps"]["speedKmh"], 54.3)
        self.assertEqual(live["sequenceNum"], 41)
        # millis() replaced by a real epoch — the app feeds this to new Date().
        self.assertGreater(live["timestampMs"], 1_700_000_000_000)

    def test_marks_device_online(self) -> None:
        self._post(headers={"X-Modem-Csq": "17"})
        self.rtdb.write_status.assert_called_once_with(DEVICE_ID, online=True, csq=17)

    def test_logs_alert_once_on_tier_increase(self) -> None:
        with mock.patch(
            "clean_run.iot.iot_router.insert_alert_event"
        ) as insert, mock.patch(
            "clean_run.iot.iot_router.record_telemetry_tick", return_value=(42, 0)
        ):
            self._post()
        insert.assert_called_once()
        self.assertEqual(insert.call_args[0][0]["alert_tier"], 2)

    def test_does_not_relog_while_tier_is_unchanged(self) -> None:
        """A driver drowsy for a minute is 20 POSTs but one alert."""
        with mock.patch(
            "clean_run.iot.iot_router.insert_alert_event"
        ) as insert, mock.patch(
            "clean_run.iot.iot_router.record_telemetry_tick", return_value=(43, 2)
        ):
            self._post()
        insert.assert_not_called()
        self.rtdb.append_alert.assert_not_called()

    def test_rejects_missing_credentials(self) -> None:
        response = self.client.post("/iot/telemetry", json=FIRMWARE_PAYLOAD)
        self.assertEqual(response.status_code, 401)

    def test_rejects_bad_secret(self) -> None:
        with mock.patch(
            "clean_run.iot.iot_router.get_device_by_secret", return_value=None
        ):
            response = self._post()
        self.assertEqual(response.status_code, 401)
        self.rtdb.write_live.assert_not_called()

    def test_rejects_body_impersonating_another_device(self) -> None:
        response = self.client.post(
            "/iot/telemetry",
            json=FIRMWARE_PAYLOAD,
            headers={"X-Device-Id": "ESP32-MAC-000000000000", "X-Device-Secret": DEVICE_SECRET},
        )
        self.assertEqual(response.status_code, 403)
        self.rtdb.write_live.assert_not_called()

    def test_reports_unavailable_so_device_queues_and_retries(self) -> None:
        self.rtdb.write_live.side_effect = RuntimeError("FIREBASE_DATABASE_URL is not set")
        response = self._post()
        # 503, not 500: the firmware requeues the reading rather than dropping it.
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
