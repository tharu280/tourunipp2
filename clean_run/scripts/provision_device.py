"""Provision an ESP32 safety hub: mint its credentials and its registration QR.

create_device_registration_ticket() has existed in repository.py since the IoT
module was written, but nothing ever called it — no route, no CLI. That left the
mobile app's QR scanner with no QR to scan and made device registration
unreachable. This is the missing caller.

Usage
-----
    cd backend
    python -m clean_run.scripts.provision_device \
        --mac F4:2D:C9:71:8A:60 \
        --label "Demo vehicle" \
        --owner-user-id <mongo user id>

The MAC is the one the hub prints at boot:

    📡 MAIN ESP32 MAC Address: F4:2D:C9:71:8A:60

It becomes the device_id verbatim (as ``ESP32-MAC-F42DC9718A60``), matching what
computeDeviceId() derives in the firmware. That is the whole point of using the
MAC rather than a UUID: no provisioning sketch, no NVM write, nothing to keep in
sync between a bench session and the database.

Two secrets come out, and they go to different places:

    device_secret        -> firmware secrets.h (never leaves the vehicle)
    registration_secret  -> the QR code the owner scans, once

Render the QR JSON with any encoder, e.g.:

    python -m clean_run.scripts.provision_device ... --qr-out device.png
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from clean_run.iot.repository import create_device_registration_ticket

_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-]?[0-9A-Fa-f]{2}){5}$")


def device_id_from_mac(mac: str) -> str:
    """``F4:2D:C9:71:8A:60`` -> ``ESP32-MAC-F42DC9718A60``.

    Mirrors computeDeviceId() in the esp32-main sketch, which uppercases
    WiFi.macAddress() and strips the colons. Keep the two in step.
    """
    if not _MAC_RE.match(mac):
        raise ValueError(
            f"{mac!r} is not a MAC address. Expected something like F4:2D:C9:71:8A:60"
        )
    return "ESP32-MAC-" + re.sub(r"[:-]", "", mac).upper()


def _write_qr_png(payload: str, path: str) -> bool:
    try:
        import qrcode  # optional dependency — not in requirements.txt
    except ImportError:
        return False
    qrcode.make(payload).save(path)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Provision an ESP32 safety hub and emit its registration QR payload.",
    )
    parser.add_argument(
        "--mac",
        required=True,
        help="Hub MAC address as printed on its serial monitor at boot.",
    )
    parser.add_argument("--label", required=True, help="Human-readable device name.")
    parser.add_argument(
        "--owner-user-id",
        required=True,
        help="Mongo user id that will own this device.",
    )
    parser.add_argument(
        "--qr-out",
        default=None,
        help="Optional path to write the QR code as a PNG (needs `pip install qrcode[pil]`).",
    )
    args = parser.parse_args(argv)

    try:
        device_id = device_id_from_mac(args.mac)
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    ticket = create_device_registration_ticket(
        label=args.label,
        owner_user_id=args.owner_user_id,
        device_id=device_id,
    )

    # Exactly the shape DeviceRegistrationScreen.tsx validates before accepting
    # a scan: {v, device_id, secret}. Any drift here breaks the scanner silently.
    qr_payload = json.dumps(
        {"v": 1, "device_id": device_id, "secret": ticket["registration_secret"]},
        separators=(",", ":"),
    )

    print()
    print("=" * 68)
    print(f"  Device provisioned: {args.label}")
    print("=" * 68)
    print()
    print(f"  device_id     {device_id}")
    print()
    print("  1. Paste into the firmware's secrets.h, then reflash:")
    print()
    print(f'     #define DEVICE_SECRET "{ticket["device_secret"]}"')
    print()
    print("  2. Encode this as a QR code for the owner to scan (one use only):")
    print()
    print(f"     {qr_payload}")
    print()

    if args.qr_out:
        if _write_qr_png(qr_payload, args.qr_out):
            print(f"  QR code written to {args.qr_out}")
        else:
            print("  --qr-out needs the qrcode package: pip install 'qrcode[pil]'")
        print()

    print("  The device_secret is shown once and is not recoverable from the app.")
    print("=" * 68)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
