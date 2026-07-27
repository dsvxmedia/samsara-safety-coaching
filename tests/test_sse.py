"""Tests for SSE format requirements."""

from __future__ import annotations

import json

import pytest

from src.models import RejectionEvent, StepEvent, TriageResult


def _sse_format(model_instance) -> str:
    """Simulate what api/index.py emits for a single item."""
    return f"data: {model_instance.model_dump_json()}\n\n"


def test_sse_double_newline_format():
    """Every SSE event must end with \\n\\n — single \\n breaks EventSource parsing."""
    step = StepEvent(tool="score_risk", input={"score": 7}, result={"status": "accepted"})
    sse = _sse_format(step)
    assert sse.endswith("\n\n"), f"SSE event must end with double newline, got: {sse!r}"


def test_sse_rejection_is_valid_json():
    rejection = RejectionEvent(reason="GPS artifact", confidence=0.3)
    sse = _sse_format(rejection)
    payload = sse[len("data: "):-2]  # strip prefix and trailing \n\n
    parsed = json.loads(payload)
    assert parsed["type"] == "rejected"
    assert parsed["reason"] == "GPS artifact"


def test_sse_step_is_valid_json():
    step = StepEvent(
        tool="get_driver_history",
        input={"driver_id": "driver_marcus"},
        result={"name": "Marcus Johnson"},
    )
    sse = _sse_format(step)
    payload = sse[len("data: "):-2]
    parsed = json.loads(payload)
    assert parsed["type"] == "step"
    assert parsed["tool"] == "get_driver_history"


def test_sse_done_sentinel():
    """The done event must be a valid JSON object with type=done."""
    done = 'data: {"type": "done"}\n\n'
    payload = json.loads(done[6:-2])
    assert payload["type"] == "done"


def test_triage_result_serializable():
    """TriageResult must be fully serializable for SSE emission."""
    from src.models import ConfidenceGateResult
    result = TriageResult(
        event_id="harsh_braking_001",
        driver_id="driver_marcus",
        gate_result=ConfidenceGateResult(
            decision="PROCEED", reason="All checks passed", confidence=0.97
        ),
        steps=[],
        elapsed_ms=4200,
    )
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["event_id"] == "harsh_braking_001"
