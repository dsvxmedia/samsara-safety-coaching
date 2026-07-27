"""Tests for the pre-flight confidence gate — pure Python, no LLM calls."""

from __future__ import annotations

import pytest

from src.data.events import EVENTS, SafetyEvent
from src.tools.confidence_gate import confidence_gate


def test_shadow_trigger_rejected():
    """GPS artifact (parking structure) must be rejected before reaching the Claude loop."""
    event = EVENTS["shadow_trigger_007"]
    result = confidence_gate(event)
    assert result.decision == "REJECT"


def test_ambiguous_rejected():
    """Conflicting signals (high G-force at/below speed limit, moderate cam confidence) → REJECT."""
    event = EVENTS["ambiguous_008"]
    result = confidence_gate(event)
    assert result.decision == "REJECT"


def test_high_confidence_proceeds():
    """Legitimate high-risk event must pass the gate."""
    event = EVENTS["harsh_braking_001"]
    result = confidence_gate(event)
    assert result.decision == "PROCEED"


def test_low_camera_confidence_rejects():
    event = SafetyEvent(
        event_id="test_low_cam",
        driver_id=None,
        event_type="harsh_braking",
        timestamp="2026-01-01T00:00:00",
        location="Test",
        speed_mph=40.0,
        speed_limit_mph=35.0,
        deceleration_g=0.8,
        duration_seconds=2.0,
        gps_variance=5.0,
        camera_confidence=0.3,  # below 0.5 threshold
        notes="",
    )
    result = confidence_gate(event)
    assert result.decision == "REJECT"
    assert "camera confidence" in result.reason.lower()


def test_high_gps_variance_rejects():
    event = SafetyEvent(
        event_id="test_gps",
        driver_id=None,
        event_type="harsh_braking",
        timestamp="2026-01-01T00:00:00",
        location="Tunnel",
        speed_mph=30.0,
        speed_limit_mph=35.0,
        deceleration_g=0.6,
        duration_seconds=2.0,
        gps_variance=25.0,  # above 20m threshold
        camera_confidence=0.9,
        notes="",
    )
    result = confidence_gate(event)
    assert result.decision == "REJECT"
    assert "gps" in result.reason.lower()


def test_sub_5mph_rejects():
    event = SafetyEvent(
        event_id="test_slow",
        driver_id=None,
        event_type="harsh_braking",
        timestamp="2026-01-01T00:00:00",
        location="Parking lot",
        speed_mph=3.0,
        speed_limit_mph=10.0,
        deceleration_g=0.5,
        duration_seconds=1.0,
        gps_variance=5.0,
        camera_confidence=0.85,
        notes="",
    )
    result = confidence_gate(event)
    assert result.decision == "REJECT"
    assert "5 mph" in result.reason


def test_all_six_canonical_proceed():
    """Every canonical event (not adversarial) must pass the gate."""
    canonical = [
        "harsh_braking_001",
        "speeding_low_002",
        "phone_distraction_003",
        "following_close_004",
        "drowsy_driving_005",
        "harsh_braking_006",
    ]
    for event_id in canonical:
        event = EVENTS[event_id]
        result = confidence_gate(event)
        assert result.decision == "PROCEED", f"{event_id} should PROCEED, got REJECT: {result.reason}"
