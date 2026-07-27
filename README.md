# Samsara AI Safety Coaching Automator

A working demo of Samsara's "Safety Coaching for Lean Teams" product — an autonomous agent that triages dashcam safety events, scores risk severity, and generates personalized coaching content. Low-risk events get self-review prompts. High-risk events get manager coaching scripts. False-trigger events get rejected without any LLM call.

```
$ python demo.py --all

Running 8 events through triage agent…

  harsh_braking_001              Marcus        9/10   COACHING
  speeding_low_002               Sarah         2/10   SELF_REVIEW
  phone_distraction_003          Devon         10/10  IMMEDIATE
  following_close_004            Maria         5/10   COACHING
  drowsy_driving_005             James         8/10   COACHING
  harsh_braking_006              Devon         7/10   COACHING
  shadow_trigger_007             —             —      REJECTED   ← pre-flight
  ambiguous_008                  —             —      REJECTED   ← pre-flight

Summary:
  6 events triaged   (4.4s avg)
  2 rejected by confidence gate (0.09s avg)  ← not LLM calls
  Estimated cost: ~$0.048 for full run
```

The 0.09s on rejected events is the point: the `confidence_gate` is a pure-Python pre-flight check, not a model call. Coaching on GPS artifacts or intentional stops destroys manager trust.

---

## Quick Start

```bash
# 1. Install
pip install -e .

# 2. Set API key
cp .env.example .env.local
# edit .env.local and add your ANTHROPIC_API_KEY

# 3. Run
python demo.py --event harsh_braking_001        # single event, streams steps
python demo.py --event shadow_trigger_007        # watch the gate reject in 0.09s
python demo.py --all                            # all 8 events, summary table
python demo.py --event harsh_braking_001 --json # machine-readable output

# Web UI
uvicorn api.index:app --reload
# → http://localhost:8000
```

---

## Architecture

```
Safety Event
     │
     ▼
confidence_gate()          ← pure Python, 0.1s — REJECT noisy events here
     │ PROCEED
     ▼
Claude tool loop (claude-sonnet-4-6)
  1. get_driver_history()  ← 90-day record, trend, coaching count
  2. get_event_context()   ← speed, G-force, camera confidence
  3. get_route_conditions() ← road type, hazards, time of day
  4. score_risk()          ← Pydantic structured output, 1-10 scale
     │
     ├── score 1-3  → create_self_review_prompt()
     └── score 4-10 → generate_coaching_script()
```

**Key patterns:**
- **Pre-flight gate**: rule-based Python, structurally impossible for Claude to skip
- **Tool-as-schema**: `RiskScore.model_json_schema()` registered as the tool's `input_schema`, `tool_choice` forces the call, Pydantic validates the result
- **Message accumulation**: both `assistant` content and `tool_result` appended to `messages` manually each step — required for correct multi-turn tool loops
- **SSE streaming**: `StreamingResponse` with `X-Accel-Buffering: no` (Vercel buffering fix), double `\n\n` after each event

---

## Event Routing

| Score | Category | Routing |
|-------|----------|---------|
| 1–3 | LOW | Self-review prompt (3 reflection questions + video clip) |
| 4–6 | MEDIUM | Manager coaching script (concise, 3-step) |
| 7–9 | HIGH | Full coaching script + escalation note |
| 10 | CRITICAL | Immediate intervention + mandatory supervisor review |
| — | — | REJECTED by confidence gate (no LLM call) |

---

## Test Suite

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

15 tests covering all routing paths, loop termination guard, message accumulation structure, SSE format, and gate bypass impossibility.

---

## Evaluation

See [docs/EVALUATION.md](docs/EVALUATION.md) for proposed metrics, failure taxonomy, A/B test design, and production feedback loop.

---

## Stack

- Python 3.12 + FastAPI + Anthropic Python SDK
- Pydantic v2 for all schemas
- Jinja2 templates (minimal UI — signals AI systems engineer, not frontend engineer)
- Vercel Python runtime (`@vercel/python`)
- Model: `claude-sonnet-4-6`
