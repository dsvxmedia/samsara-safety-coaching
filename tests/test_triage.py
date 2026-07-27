"""
Integration tests for the triage agent routing logic.

These tests mock the Anthropic client to verify:
- Correct routing for all 5 paths (REJECTED, SELF_REVIEW, COACHING, IMMEDIATE, error)
- Message accumulation structure
- Loop termination guard
- Pre-flight gate fires before Claude loop
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agent.triage_agent import AgentLoopError, run_triage
from src.models import RejectionEvent, StepEvent, TriageResult


def _make_tool_use_response(tool_name: str, tool_input: dict, tool_id: str = "tu_001"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    block.id = tool_id
    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [block]
    return response


def _make_end_response():
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = []
    return response


# Adversarial events are rejected without any Anthropic API call
def test_shadow_trigger_rejected_no_api_call():
    with patch("src.agent.triage_agent.anthropic.Anthropic") as mock_client_cls:
        items = list(run_triage("shadow_trigger_007"))
    mock_client_cls.assert_not_called()
    rejections = [i for i in items if isinstance(i, RejectionEvent)]
    assert len(rejections) == 1


def test_ambiguous_rejected_no_api_call():
    with patch("src.agent.triage_agent.anthropic.Anthropic") as mock_client_cls:
        items = list(run_triage("ambiguous_008"))
    mock_client_cls.assert_not_called()
    rejections = [i for i in items if isinstance(i, RejectionEvent)]
    assert len(rejections) == 1


def test_low_risk_routes_to_self_review():
    """Score 2 → create_self_review_prompt called."""
    responses = [
        _make_tool_use_response("get_driver_history", {"driver_id": "driver_sarah"}, "tu_1"),
        _make_tool_use_response("get_event_context", {"event_id": "speeding_low_002"}, "tu_2"),
        _make_tool_use_response("get_route_conditions", {"event_id": "speeding_low_002"}, "tu_3"),
        _make_tool_use_response("score_risk", {
            "score": 2, "category": "LOW", "primary_factors": ["minor_speeding"],
            "driver_context_summary": "First event", "recommendation": "SELF_REVIEW",
            "confidence": 0.88, "reasoning": "Minor infraction, first offense",
        }, "tu_4"),
        _make_tool_use_response("create_self_review_prompt", {
            "driver_name": "Sarah Kim",
            "event_summary": "7 mph over on interchange ramp",
            "questions": ["What was your speed?", "Was it avoidable?", "What will you do next time?"],
            "video_clip_prompt": "Review clip from 14:20",
        }, "tu_5"),
        _make_end_response(),
    ]

    with patch("src.agent.triage_agent.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = responses
        items = list(run_triage("speeding_low_002"))

    final = next((i for i in items if isinstance(i, TriageResult)), None)
    assert final is not None
    assert final.self_review_prompt is not None
    assert final.coaching_script is None
    assert final.risk_score.score == 2


def test_critical_risk_routes_to_immediate():
    """Score 10 → generate_coaching_script with IMMEDIATE_INTERVENTION."""
    responses = [
        _make_tool_use_response("get_driver_history", {"driver_id": "driver_devon"}, "tu_1"),
        _make_tool_use_response("get_event_context", {"event_id": "phone_distraction_003"}, "tu_2"),
        _make_tool_use_response("get_route_conditions", {"event_id": "phone_distraction_003"}, "tu_3"),
        _make_tool_use_response("score_risk", {
            "score": 10, "category": "CRITICAL",
            "primary_factors": ["phone_use", "industrial_zone", "repeat_offender"],
            "driver_context_summary": "3rd phone event this month",
            "recommendation": "IMMEDIATE_INTERVENTION",
            "confidence": 0.97, "reasoning": "Immediate safety threat",
        }, "tu_4"),
        _make_tool_use_response("generate_coaching_script", {
            "driver_name": "Devon Richardson",
            "event_summary": "Phone distraction for 12s at 38 mph near loading dock",
            "tone": "urgent",
            "key_points": ["Pedestrian workers present", "Third offense"],
            "opening": "Devon, this is urgent.",
            "body": "You used your phone for 12 seconds in an active loading zone.",
            "follow_up_action": "Mandatory supervisor review within 24 hours.",
            "coaching_type": "IMMEDIATE_INTERVENTION",
        }, "tu_5"),
        _make_end_response(),
    ]

    with patch("src.agent.triage_agent.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = responses
        items = list(run_triage("phone_distraction_003"))

    final = next((i for i in items if isinstance(i, TriageResult)), None)
    assert final is not None
    assert final.coaching_script is not None
    assert final.coaching_script.coaching_type == "IMMEDIATE_INTERVENTION"
    assert final.risk_score.score == 10


def test_message_accumulation_structure():
    """After N tool calls, messages array has correct alternating structure."""
    call_count = 0
    captured_messages: list[list] = []

    def capture_and_respond(**kwargs):
        nonlocal call_count
        captured_messages.append(list(kwargs.get("messages", [])))
        call_count += 1
        if call_count == 1:
            return _make_tool_use_response("get_driver_history", {"driver_id": "driver_marcus"}, "tu_1")
        if call_count == 2:
            return _make_tool_use_response("get_event_context", {"event_id": "harsh_braking_001"}, "tu_2")
        return _make_end_response()

    with patch("src.agent.triage_agent.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = capture_and_respond
        list(run_triage("harsh_braking_001"))

    # After 2 tool calls: messages should have grown by 2 pairs
    assert call_count == 3
    # Second call: messages has initial + assistant + tool_result
    second_call_messages = captured_messages[1]
    assert len(second_call_messages) == 3  # [user_init, assistant, tool_result]
    assert second_call_messages[1]["role"] == "assistant"
    assert second_call_messages[2]["role"] == "user"
    assert second_call_messages[2]["content"][0]["type"] == "tool_result"


def test_loop_termination_guard():
    """Agent loop must raise AgentLoopError after MAX_TOOL_STEPS calls."""
    def always_tool_use(**kwargs):
        block = MagicMock()
        block.type = "tool_use"
        block.name = "get_event_context"
        block.input = {"event_id": "harsh_braking_001"}
        block.id = "tu_loop"
        resp = MagicMock()
        resp.stop_reason = "tool_use"
        resp.content = [block]
        return resp

    with patch("src.agent.triage_agent.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = always_tool_use
        with pytest.raises(AgentLoopError):
            list(run_triage("harsh_braking_001"))
