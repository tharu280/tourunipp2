"""IoT device integration package — Smart Driver & Vehicle Proactive Safety System.

Adds device management, Firebase custom token issuance, alert event logging,
and trip session tracking to the existing TourUni backend.

Public exports for api.py wiring:
    devices_router    — /devices prefix
    iot_router        — /iot prefix
    admin_iot_router  — /admin/iot prefix (fleet-wide admin management)
"""

from .admin_iot_router import router as admin_iot_router
from .devices_router import router as devices_router
from .iot_router import router as iot_router

__all__ = ["devices_router", "iot_router", "admin_iot_router"]
