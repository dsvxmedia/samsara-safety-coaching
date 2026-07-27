from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# String length hints are passed to Claude via the JSON schema description field.
# We do NOT use Pydantic max_length on strings — if Claude is slightly verbose,
# model_validate would silently fail and discard the entire structured output.
# Only list lengths are enforced (maxItems in JSON schema), since those affect
# downstream routing logic (primary_factors list used to build coaching content).


class RiskScore(BaseModel):
    score: int = Field(ge=1, le=10)
    category: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    primary_factors: list[str] = Field(
        max_length=5,
        description="Up to 5 key factors driving the risk score.",
    )
    driver_context_summary: str = Field(
        description="1-2 sentence summary of driver's relevant history (under 200 chars).",
    )
    recommendation: Literal["SELF_REVIEW", "MANAGER_COACHING", "IMMEDIATE_INTERVENTION"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(
        description="Reasoning for the score (under 500 chars).",
    )


class CoachingScript(BaseModel):
    driver_name: str
    event_summary: str = Field(
        description="One sentence describing what happened.",
    )
    tone: Literal["educational", "affirming", "firm", "urgent"]
    key_points: list[str] = Field(
        max_length=5,
        description="Up to 5 specific coaching points from the event.",
    )
    opening: str = Field(
        description="Opening line addressing the driver directly (under 300 chars).",
    )
    body: str = Field(
        description="Main coaching content referencing specific details (under 800 chars).",
    )
    follow_up_action: str = Field(
        description="Required follow-up action for the driver or manager (under 200 chars).",
    )
    coaching_type: Literal["MANAGER_COACHING", "IMMEDIATE_INTERVENTION"]


class SelfReviewPrompt(BaseModel):
    driver_name: str
    event_summary: str = Field(
        description="One sentence describing the event.",
    )
    questions: list[str] = Field(
        min_length=3,
        max_length=3,
        description="Exactly 3 reflection questions for the driver.",
    )
    video_clip_prompt: str = Field(
        description="Instruction for the driver to review their video clip (under 200 chars).",
    )


class ConfidenceGateResult(BaseModel):
    decision: Literal["PROCEED", "REJECT"]
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    rules: list[dict] | None = None


class StepEvent(BaseModel):
    type: str = "step"
    tool: str
    input: dict
    result: dict
    elapsed_ms: int | None = None


class RejectionEvent(BaseModel):
    type: str = "rejected"
    reason: str
    confidence: float


class TriageResult(BaseModel):
    event_id: str
    driver_id: str | None
    risk_score: RiskScore | None = None
    coaching_script: CoachingScript | None = None
    self_review_prompt: SelfReviewPrompt | None = None
    gate_result: ConfidenceGateResult
    steps: list[StepEvent]
    elapsed_ms: int
