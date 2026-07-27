#!/usr/bin/env python3
"""
Samsara AI Safety Coaching Automator — CLI Demo

Usage:
  python demo.py --event harsh_braking_001
  python demo.py --event shadow_trigger_007     # rejected by confidence gate
  python demo.py --all                          # summary table of all 8 events
  python demo.py --event harsh_braking_001 --json  # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")

# API key check at entry — fail fast with an actionable message
if not os.environ.get("ANTHROPIC_API_KEY"):
    print(
        "Error: ANTHROPIC_API_KEY is not set.\n"
        "  cp .env.example .env.local\n"
        "  # add your key to .env.local\n"
        "  python demo.py --event harsh_braking_001",
        file=sys.stderr,
    )
    sys.exit(1)

from src.agent.triage_agent import AgentLoopError, run_triage
from src.data.events import EVENTS
from src.models import RejectionEvent, StepEvent, TriageResult

# ANSI color codes for terminal output
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
GRAY = "\033[90m"
MAGENTA = "\033[95m"

CATEGORY_COLORS = {
    "LOW": GREEN,
    "MEDIUM": YELLOW,
    "HIGH": RED,
    "CRITICAL": MAGENTA,
}

ROUTE_COLORS = {
    "SELF_REVIEW": GREEN,
    "MANAGER_COACHING": YELLOW,
    "IMMEDIATE_INTERVENTION": RED,
    "REJECTED": GRAY,
}


def _color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


def _tool_label(tool_name: str) -> str:
    labels = {
        "get_driver_history": "driver_history",
        "get_event_context": "event_context",
        "get_route_conditions": "route_context",
        "score_risk": "score_risk",
        "generate_coaching_script": "coaching_script",
        "create_self_review_prompt": "self_review",
    }
    return labels.get(tool_name, tool_name)


def _print_step(step: StepEvent) -> None:
    label = _tool_label(step.tool)
    if step.tool == "score_risk":
        score = step.input.get("score", "?")
        category = step.input.get("category", "?")
        rec = step.input.get("recommendation", "?")
        color = CATEGORY_COLORS.get(str(category), "")
        print(
            f"  [{_color(label, CYAN)}] → Score: {_color(f'{score}/10', BOLD)} "
            f"{_color(category, color)} — {rec}"
        )
    elif step.tool == "generate_coaching_script":
        tone = step.input.get("tone", "?")
        opening = step.input.get("opening", "")[:80]
        print(f"  [{_color(label, CYAN)}] → tone={tone}")
        print(f"    {GRAY}{opening}…{RESET}")
    elif step.tool == "create_self_review_prompt":
        questions = step.input.get("questions", [])
        print(f"  [{_color(label, CYAN)}] → {len(questions)} reflection questions")
        for q in questions:
            print(f"    {GRAY}• {q}{RESET}")
    else:
        result_keys = list(step.result.keys())[:3]
        print(f"  [{_color(label, CYAN)}] → {', '.join(result_keys)}")


def _print_result_card(result: TriageResult) -> None:
    if result.risk_score:
        rs = result.risk_score
        cat_color = CATEGORY_COLORS.get(rs.category, "")
        print(f"\n{BOLD}Risk Score:{RESET} {_color(f'{rs.score}/10', BOLD)} "
              f"— {_color(rs.category, cat_color)}")
        print(f"Recommendation: {_color(rs.recommendation, cat_color)}")
        print(f"Confidence: {rs.confidence:.0%}")
        if rs.primary_factors:
            print("Factors:")
            for f in rs.primary_factors:
                print(f"  • {f}")

    if result.coaching_script:
        cs = result.coaching_script
        print(f"\n{BOLD}Coaching Script{RESET} ({cs.coaching_type}, tone={cs.tone}):")
        print(f"  {cs.opening}")
        print(f"  {GRAY}{cs.body[:200]}…{RESET}")
        print(f"  Follow-up: {cs.follow_up_action}")

    if result.self_review_prompt:
        srp = result.self_review_prompt
        print(f"\n{BOLD}Self-Review Prompt{RESET} for {srp.driver_name}:")
        for q in srp.questions:
            print(f"  • {q}")
        print(f"  Video: {srp.video_clip_prompt}")


def run_single_event(event_id: str, json_mode: bool = False) -> None:
    event = EVENTS.get(event_id)
    if event is None:
        print(f"Error: unknown event_id '{event_id}'", file=sys.stderr)
        print(f"Available: {', '.join(EVENTS.keys())}", file=sys.stderr)
        sys.exit(1)

    if not json_mode:
        print(f"\n{BOLD}Triaging:{RESET} {event_id} ({event.event_type})")
        print(f"Driver: {event.driver_id or 'unknown'} | Location: {event.location}\n")

    final_result: TriageResult | None = None

    try:
        for item in run_triage(event_id):
            if isinstance(item, StepEvent):
                if not json_mode:
                    _print_step(item)
            elif isinstance(item, RejectionEvent):
                if not json_mode:
                    print(f"  [{_color('confidence_gate', CYAN)}] → "
                          f"{_color('REJECTED', RED)} ({item.confidence:.2%} confidence)")
                    print(f"    {GRAY}{item.reason}{RESET}")
            elif isinstance(item, TriageResult):
                final_result = item

        if final_result is None:
            return

        if json_mode:
            print(final_result.model_dump_json(indent=2))
            return

        elapsed = final_result.elapsed_ms / 1000
        print(f"\n{_color('✓ Complete', GREEN)} ({elapsed:.1f}s)")
        _print_result_card(final_result)

    except AgentLoopError as e:
        print(f"\n{_color('Error:', RED)} {e}", file=sys.stderr)
        sys.exit(1)


def run_all_events() -> None:
    results: list[dict] = []

    print(f"\n{BOLD}Running {len(EVENTS)} events through triage agent…{RESET}\n")

    for event_id, event in EVENTS.items():
        t0 = time.perf_counter()
        route = "?"
        score_str = "—"
        category = "—"
        driver_label = event.driver_id.replace("driver_", "").title() if event.driver_id else "—"

        try:
            for item in run_triage(event_id):
                if isinstance(item, RejectionEvent):
                    route = "REJECTED"
                elif isinstance(item, TriageResult):
                    if item.risk_score:
                        score_str = f"{item.risk_score.score}/10"
                        category = item.risk_score.category
                        rec = item.risk_score.recommendation
                        route = {
                            "SELF_REVIEW": "SELF_REVIEW",
                            "MANAGER_COACHING": "COACHING",
                            "IMMEDIATE_INTERVENTION": "IMMEDIATE",
                        }.get(rec, rec)
        except (AgentLoopError, Exception) as e:
            route = "ERROR"
            score_str = "—"
            if not isinstance(e, AgentLoopError):
                import traceback
                traceback.print_exc()

        elapsed = time.perf_counter() - t0
        results.append({
            "event_id": event_id,
            "driver": driver_label,
            "score": score_str,
            "category": category,
            "route": route,
            "elapsed": elapsed,
        })

        route_color = ROUTE_COLORS.get(route, "")
        rejected_note = "  ← pre-flight" if route == "REJECTED" else ""
        print(
            f"  {event_id:<30} {driver_label:<12} {score_str:<6} "
            f"{_color(route, route_color):<20}{rejected_note}"
        )

    total_elapsed = sum(r["elapsed"] for r in results)
    triaged = [r for r in results if r["route"] != "REJECTED"]
    rejected = [r for r in results if r["route"] == "REJECTED"]

    avg_triaged = (
        sum(r["elapsed"] for r in triaged) / len(triaged) if triaged else 0
    )
    avg_rejected = (
        sum(r["elapsed"] for r in rejected) / len(rejected) if rejected else 0
    )

    print(f"\n{BOLD}Summary:{RESET}")
    if triaged:
        print(f"  {len(triaged)} events triaged   ({avg_triaged:.1f}s avg)")
    if rejected:
        print(f"  {len(rejected)} rejected by confidence gate ({avg_rejected:.2f}s avg)  ← not LLM calls")

    # Rough cost estimate: ~2k input + 500 output tokens per triaged event @ claude-sonnet-4-6
    est_cost = len(triaged) * ((2000 * 3 + 500 * 15) / 1_000_000)
    print(f"  Estimated cost: ~${est_cost:.3f} for full run")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Samsara AI Safety Coaching Automator — demo CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--event", metavar="EVENT_ID", help="Triage a single event by ID")
    group.add_argument("--all", action="store_true", help="Run all 8 events and print summary table")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON (with --event)")

    args = parser.parse_args()

    if args.all:
        run_all_events()
    else:
        run_single_event(args.event, json_mode=args.json)


if __name__ == "__main__":
    main()
