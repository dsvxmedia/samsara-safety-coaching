"""
Rule-based pre-flight gate — runs before the Claude tool loop.

This is pure Python with no LLM call. That's deliberate: if the gate itself
required a model round-trip, adversarial events would waste time and tokens
before being rejected. The 0.1s timing visible in --all output is the proof.
"""

from __future__ import annotations

from src.data.events import SafetyEvent
from src.models import ConfidenceGateResult


def _build_rules(event: SafetyEvent) -> list[dict]:
    """Evaluate all 4 gate rules and return a structured list for UI display."""
    r1 = event.camera_confidence >= 0.5
    r2 = event.gps_variance <= 20.0
    r3 = event.speed_mph >= 5.0
    r4_trigger = (
        event.deceleration_g is not None
        and event.deceleration_g > 0.7
        and event.speed_mph <= event.speed_limit_mph
        and event.camera_confidence < 0.90
    )
    r4 = not r4_trigger

    g_display = (
        f"{event.deceleration_g:.2f}G at {event.speed_mph:.0f} mph "
        f"(limit {event.speed_limit_mph:.0f} mph)"
        if event.deceleration_g is not None
        else "N/A — no deceleration data"
    )

    return [
        {
            "name": "Camera confidence",
            "passed": r1,
            "value_display": f"{event.camera_confidence:.0%} (threshold: ≥ 50%)",
        },
        {
            "name": "GPS variance",
            "passed": r2,
            "value_display": f"{event.gps_variance:.1f} m (threshold: ≤ 20 m)",
        },
        {
            "name": "Minimum speed",
            "passed": r3,
            "value_display": f"{event.speed_mph:.1f} mph (threshold: ≥ 5 mph)",
        },
        {
            "name": "No conflicting signals",
            "passed": r4,
            "value_display": g_display,
        },
    ]


def confidence_gate(event: SafetyEvent) -> ConfidenceGateResult:
    """Return REJECT with reason if the event is a false trigger; PROCEED otherwise."""
    rules = _build_rules(event)

    # Rule 1: dashcam detection confidence too low to trust
    if event.camera_confidence < 0.5:
        return ConfidenceGateResult(
            decision="REJECT",
            reason=(
                f"Camera confidence {event.camera_confidence:.2f} below threshold 0.50 — "
                "detection unreliable, likely sensor artifact"
            ),
            confidence=event.camera_confidence,
            rules=rules,
        )

    # Rule 2: GPS variance too high — indoors, tunnel, or heavy occlusion
    if event.gps_variance > 20.0:
        return ConfidenceGateResult(
            decision="REJECT",
            reason=(
                f"GPS variance {event.gps_variance:.1f}m exceeds 20m threshold — "
                "likely indoor or heavily occluded location; event may be spurious"
            ),
            confidence=1.0 - min(event.gps_variance / 50.0, 0.99),
            rules=rules,
        )

    # Rule 3: sub-5 mph — parking maneuver, not a road safety event
    if event.speed_mph < 5.0:
        return ConfidenceGateResult(
            decision="REJECT",
            reason=(
                f"Speed {event.speed_mph:.1f} mph below 5 mph threshold — "
                "likely parking maneuver, not a road safety event"
            ),
            confidence=0.95,
            rules=rules,
        )

    # Rule 4: conflicting signals — high G-force but at/below speed limit with
    # moderate camera confidence suggests an intentional controlled stop (e.g.,
    # yielding for emergency vehicle, stop sign, pedestrian). Coaching on a
    # correct driving behavior causes manager-trust erosion.
    if (
        event.deceleration_g is not None
        and event.deceleration_g > 0.7
        and event.speed_mph <= event.speed_limit_mph
        and event.camera_confidence < 0.90
    ):
        return ConfidenceGateResult(
            decision="REJECT",
            reason=(
                f"Conflicting signals: {event.deceleration_g:.2f}G deceleration but speed "
                f"({event.speed_mph:.0f} mph) at/below limit ({event.speed_limit_mph:.0f} mph) "
                "with camera confidence < 0.90 — likely intentional controlled stop"
            ),
            confidence=event.camera_confidence,
            rules=rules,
        )

    return ConfidenceGateResult(
        decision="PROCEED",
        reason="All confidence checks passed",
        confidence=event.camera_confidence,
        rules=rules,
    )
