from __future__ import annotations

from src.data.events import EVENTS


def get_event_context(event_id: str) -> dict:
    """Return telemetry breakdown and severity factors for the given event."""
    event = EVENTS.get(event_id)
    if event is None:
        return {"found": False, "event_id": event_id, "error": "Event not found"}

    speed_delta = event.speed_mph - event.speed_limit_mph
    over_limit = speed_delta > 0

    severity_factors = []
    if event.deceleration_g is not None and event.deceleration_g >= 0.8:
        severity_factors.append(f"Extreme deceleration: {event.deceleration_g:.2f}G")
    elif event.deceleration_g is not None and event.deceleration_g >= 0.6:
        severity_factors.append(f"High deceleration: {event.deceleration_g:.2f}G")
    if over_limit:
        severity_factors.append(f"Over speed limit by {speed_delta:.1f} mph")
    if event.event_type == "phone_distraction":
        severity_factors.append("Active phone use while driving")
    if event.event_type == "drowsy_driving":
        severity_factors.append("Drowsiness detected — high crash risk")
    if event.camera_confidence >= 0.95:
        severity_factors.append(f"High-confidence detection ({event.camera_confidence:.2f})")

    return {
        "found": True,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "location": event.location,
        "speed_mph": event.speed_mph,
        "speed_limit_mph": event.speed_limit_mph,
        "mph_over_limit": round(speed_delta, 1) if over_limit else 0,
        "deceleration_g": event.deceleration_g,
        "duration_seconds": event.duration_seconds,
        "camera_confidence": event.camera_confidence,
        "severity_factors": severity_factors,
        "notes": event.notes,
    }
