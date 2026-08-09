"""IoT device integration package — Smart Driver & Vehicle Proactive Safety System.

Adds device management, Firebase custom token issuance, alert event logging,
and trip session tracking to the existing TourUni backend.

Public exports for api.py wiring:
    devices_router  — /devices prefix
    iot_router      — /iot prefix
"""

from .devices_router import router as devices_router
from .iot_router import router as iot_router

__all__ = ["devices_router", "iot_router"]
