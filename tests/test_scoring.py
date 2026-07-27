"""Tests for Pydantic schema validation on structured tool outputs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import CoachingScript, RiskScore, SelfReviewPrompt


def test_risk_score_valid():
    rs = RiskScore(
        score=7,
        category="HIGH",
        primary_factors=["speeding", "wet_road"],
        driver_context_summary="Driver has worsening trend",
        recommendation="MANAGER_COACHING",
        confidence=0.92,
        reasoning="High deceleration in school zone",
    )
    assert rs.score == 7
    assert rs.category == "HIGH"


def test_risk_score_out_of_range_rejects():
    with pytest.raises(ValidationError):
        RiskScore(
            score=11,  # exceeds 1-10
            category="HIGH",
            primary_factors=[],
            driver_context_summary="",
            recommendation="MANAGER_COACHING",
            confidence=0.9,
            reasoning="",
        )


def test_risk_score_zero_rejects():
    with pytest.raises(ValidationError):
        RiskScore(
            score=0,  # below 1
            category="LOW",
            primary_factors=[],
            driver_context_summary="",
            recommendation="SELF_REVIEW",
            confidence=0.8,
            reasoning="",
        )


def test_boundary_score_3_is_low():
    rs = RiskScore(
        score=3,
        category="LOW",
        primary_factors=["minor_speeding"],
        driver_context_summary="First event",
        recommendation="SELF_REVIEW",
        confidence=0.85,
        reasoning="Minor infraction",
    )
    assert rs.category == "LOW"
    assert rs.recommendation == "SELF_REVIEW"


def test_boundary_score_4_is_medium():
    rs = RiskScore(
        score=4,
        category="MEDIUM",
        primary_factors=["following_too_close"],
        driver_context_summary="Some history",
        recommendation="MANAGER_COACHING",
        confidence=0.88,
        reasoning="Moderate risk",
    )
    assert rs.category == "MEDIUM"


def test_coaching_script_valid():
    cs = CoachingScript(
        driver_name="Marcus Johnson",
        event_summary="Harsh braking at 71 mph",
        tone="firm",
        key_points=["Speed was 26 mph over limit", "School zone"],
        opening="Marcus, let's talk about what happened on Tuesday.",
        body="You were traveling at 71 mph in a 45 mph school zone.",
        follow_up_action="Review within 5 business days with supervisor.",
        coaching_type="MANAGER_COACHING",
    )
    assert cs.tone == "firm"
    assert cs.coaching_type == "MANAGER_COACHING"


def test_self_review_requires_three_questions():
    with pytest.raises(ValidationError):
        SelfReviewPrompt(
            driver_name="Sarah Kim",
            event_summary="Speeding on ramp",
            questions=["Only one question"],  # min_length=3
            video_clip_prompt="Watch clip at 14:20",
        )


def test_confidence_invalid_range():
    with pytest.raises(ValidationError):
        RiskScore(
            score=5,
            category="MEDIUM",
            primary_factors=[],
            driver_context_summary="",
            recommendation="MANAGER_COACHING",
            confidence=1.5,  # > 1.0
            reasoning="",
        )
