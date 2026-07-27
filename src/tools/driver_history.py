from __future__ import annotations

from src.data.drivers import DRIVERS


def get_driver_history(driver_id: str) -> dict:
    """Return 90-day driver history for the given driver ID."""
    profile = DRIVERS.get(driver_id)
    if profile is None:
        return {
            "found": False,
            "driver_id": driver_id,
            "error": "Driver not found in system",
        }
    return {
        "found": True,
        "driver_id": profile.driver_id,
        "name": profile.name,
        "hire_date": profile.hire_date,
        "vehicle_class": profile.vehicle_class,
        "events_last_90_days": profile.events_90d,
        "events_last_30_days": profile.events_30d,
        "coaching_sessions_total": profile.coaching_sessions,
        "trend": profile.trend,
        "last_coaching_date": profile.last_coaching_date,
        "summary": profile.notes,
    }
