"""
Core triage agent — three functions, one clear job each:

  run_triage()      — public entry point, yields StepEvent / RejectionEvent
  _preflight_gate() — pure-Python confidence check, no LLM call
  _tool_loop()      — Anthropic SDK tool_use loop with explicit message accumulation
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Generator
from typing import Any

import anthropic
from pydantic import ValidationError

from src.data.events import EVENTS, SafetyEvent
from src.models import (
    CoachingScript,
    ConfidenceGateResult,
    RejectionEvent,
    RiskScore,
    SelfReviewPrompt,
    StepEvent,
    TriageResult,
)
from src.tools.confidence_gate import confidence_gate
from src.tools.driver_history import get_driver_history
from src.tools.event_context import get_event_context
from src.tools.route_context import get_route_conditions

MODEL = "claude-sonnet-4-6"
MAX_TOOL_STEPS = 8

# Tool-as-schema: Pydantic model JSON schemas registered as tool input_schema.
# Claude is forced to call these tools, giving us type-safe structured outputs.
TOOLS: list[dict] = [
    {
        "name": "get_driver_history",
        "description": "Retrieve the driver's 90-day safety event history, coaching count, and trend.",
        "input_schema": {
            "type": "object",
            "properties": {
                "driver_id": {
                    "type": "string",
                    "description": "The driver ID from the safety event.",
                }
            },
            "required": ["driver_id"],
        },
    },
    {
        "name": "get_event_context",
        "description": "Retrieve telemetry breakdown and severity factors for the safety event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "The event ID to look up.",
                }
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "get_route_conditions",
        "description": "Retrieve road type, weather, and known hazard context for the event location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "The event ID to look up route conditions for.",
                }
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "score_risk",
        "description": (
            "Score the risk severity of this safety event on a 1–10 scale and select a routing action. "
            "Call this after gathering driver history, event context, and route conditions."
        ),
        "input_schema": RiskScore.model_json_schema(),
    },
    {
        "name": "generate_coaching_script",
        "description": (
            "Generate a personalized coaching script for the driver. "
            "Call this when score >= 4 (MEDIUM, HIGH, or CRITICAL)."
        ),
        "input_schema": CoachingScript.model_json_schema(),
    },
    {
        "name": "create_self_review_prompt",
        "description": (
            "Create a self-review prompt with 3 reflection questions for the driver. "
            "Call this when score 1–3 (LOW)."
        ),
        "input_schema": SelfReviewPrompt.model_json_schema(),
    },
]

SYSTEM_PROMPT = """You are a fleet safety triage agent. Your job is to assess a safety event
captured by a dashcam and produce either a personalized coaching script or a self-review
prompt for the driver.

## Workflow — follow in order, no skipping

1. Call get_driver_history(driver_id) to understand the driver's 90-day record and trend.
2. Call get_event_context(event_id) to get telemetry details and severity factors.
3. Call get_route_conditions(event_id) to get road type, hazards, and context.
4. Call score_risk(...) with all three context sources in mind. Use this scale:
   - 1–3 → LOW: minor infraction, no pattern, low-risk conditions
   - 4–6 → MEDIUM: clear infraction or mild pattern
   - 7–9 → HIGH: dangerous behavior or strong pattern in hazardous context
   - 10 → CRITICAL: immediate safety threat
5. Based on the score:
   - Score 1–3 (LOW) → Call create_self_review_prompt(...)
   - Score 4–10 (MEDIUM/HIGH/CRITICAL) → Call generate_coaching_script(...)

## Personalization rules

- Reference the driver's actual name, the event timestamp, and specific details.
- Tone by trend: IMPROVING → affirming; STABLE → educational; WORSENING → firm.
- Coaching count: first offense → educational; 3+ sessions with no improvement → accountability-focused.
- coaching_type: score 10 → IMMEDIATE_INTERVENTION; score 4–9 → MANAGER_COACHING.

## Output quality

Be specific. Vague coaching ("drive safely") is worse than no coaching.
Reference the actual numbers: speed, G-force, duration, route conditions."""


class AgentLoopError(Exception):
    pass


def run_triage(event_id: str) -> Generator[StepEvent | RejectionEvent | TriageResult, None, None]:
    """
    Main entry point. Yields streaming step events, then a final TriageResult.

    Callers can consume steps for real-time display and use the terminal TriageResult
    for structured storage. Both CLI and FastAPI SSE use this same generator.
    """
    event = EVENTS.get(event_id)
    if event is None:
        raise ValueError(f"Unknown event_id: {event_id!r}")

    start_ms = int(time.time() * 1000)
    steps: list[StepEvent] = []

    gate_result = _preflight_gate(event)

    if gate_result.decision == "REJECT":
        rejection = RejectionEvent(
            reason=gate_result.reason,
            confidence=gate_result.confidence,
        )
        yield rejection
        yield TriageResult(
            event_id=event_id,
            driver_id=event.driver_id,
            gate_result=gate_result,
            steps=steps,
            elapsed_ms=int(time.time() * 1000) - start_ms,
        )
        return

    for step_or_result in _tool_loop(event, gate_result):
        if isinstance(step_or_result, StepEvent):
            steps.append(step_or_result)
            yield step_or_result
        elif isinstance(step_or_result, TriageResult):
            final = TriageResult(
                event_id=step_or_result.event_id,
                driver_id=step_or_result.driver_id,
                risk_score=step_or_result.risk_score,
                coaching_script=step_or_result.coaching_script,
                self_review_prompt=step_or_result.self_review_prompt,
                gate_result=gate_result,
                steps=steps,
                elapsed_ms=int(time.time() * 1000) - start_ms,
            )
            yield final


def _preflight_gate(event: SafetyEvent) -> ConfidenceGateResult:
    """
    Pure-Python confidence check — no LLM call.

    Structured to be structurally impossible to skip: it runs synchronously before
    any Anthropic API call is made. The 0.1s timing in --all output proves it.
    """
    return confidence_gate(event)


def _tool_loop(
    event: SafetyEvent,
    gate_result: ConfidenceGateResult,
) -> Generator[StepEvent | TriageResult, None, None]:
    """
    Anthropic tool_use loop with explicit message accumulation.

    Messages are manually appended after each tool call (assistant content + tool_result).
    Without this, the model re-derives context from scratch each step or loops infinitely.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    driver_id = event.driver_id or "unknown"
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Triage this safety event.\n\n"
                f"event_id: {event.event_id}\n"
                f"driver_id: {driver_id}\n"
                f"event_type: {event.event_type}\n"
                f"timestamp: {event.timestamp}\n"
                f"location: {event.location}\n\n"
                "Follow the workflow in the system prompt. Begin with get_driver_history."
            ),
        }
    ]

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
    )

    risk_score: RiskScore | None = None
    coaching_script: CoachingScript | None = None
    self_review_prompt: SelfReviewPrompt | None = None
    step_count = 0

    while response.stop_reason == "tool_use":
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        # Collect all tool_result blocks for this turn before appending to messages.
        # Claude may return multiple tool_use blocks in one response (parallel calls);
        # every tool_use id must have a corresponding tool_result in the SAME next message.
        tool_results = []
        for tool_use_block in tool_use_blocks:
            tool_name = tool_use_block.name
            tool_input = tool_use_block.input

            result = _execute_tool(tool_name, tool_input)

            # Parse structured outputs from tool-as-schema calls
            if tool_name == "score_risk":
                try:
                    risk_score = RiskScore.model_validate(tool_input)
                except ValidationError:
                    pass
            elif tool_name == "generate_coaching_script":
                try:
                    coaching_script = CoachingScript.model_validate(tool_input)
                except ValidationError:
                    pass
            elif tool_name == "create_self_review_prompt":
                try:
                    self_review_prompt = SelfReviewPrompt.model_validate(tool_input)
                except ValidationError:
                    pass

            yield StepEvent(tool=tool_name, input=tool_input, result=result)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_block.id,
                "content": json.dumps(result),
            })

        # CRITICAL: accumulate both sides before next API call.
        # All tool_results for this turn go in a single user message.
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        step_count += len(tool_use_blocks)
        if step_count >= MAX_TOOL_STEPS:
            raise AgentLoopError(
                f"Exceeded {MAX_TOOL_STEPS} tool steps — possible loop. "
                f"Last tool: {tool_use_blocks[-1].name}"
            )

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

    yield TriageResult(
        event_id=event.event_id,
        driver_id=event.driver_id,
        risk_score=risk_score,
        coaching_script=coaching_script,
        self_review_prompt=self_review_prompt,
        gate_result=gate_result,
        steps=[],  # caller assembles from yielded StepEvents
        elapsed_ms=0,  # caller sets this
    )


def _execute_tool(tool_name: str, tool_input: dict[str, Any]) -> dict:
    """Dispatch tool call to the appropriate Python function."""
    if tool_name == "get_driver_history":
        return get_driver_history(tool_input["driver_id"])
    elif tool_name == "get_event_context":
        return get_event_context(tool_input["event_id"])
    elif tool_name == "get_route_conditions":
        return get_route_conditions(tool_input["event_id"])
    elif tool_name in ("score_risk", "generate_coaching_script", "create_self_review_prompt"):
        # Tool-as-schema pattern: Claude fills the schema, we validate it.
        # The "result" here is just an ack — the real value is already in tool_input.
        return {"status": "accepted", "tool": tool_name}
    else:
        return {"error": f"Unknown tool: {tool_name}"}
