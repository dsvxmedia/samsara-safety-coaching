# Samsara AI Safety Coaching Automator

[![CI](https://github.com/dsvxmedia/samsara-safety-coaching/actions/workflows/ci.yml/badge.svg)](https://github.com/dsvxmedia/samsara-safety-coaching/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![Model](https://img.shields.io/badge/model-claude--sonnet--4--6-orange.svg)
![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)

Autonomous agent that triages dashcam safety events, scores risk severity, and generates personalized coaching content. Built as a proof-of-concept for Samsara's "Safety Coaching for Lean Teams" use case.

False-trigger events are rejected before any LLM call. Low-risk events get self-review prompts. High-risk events get manager coaching scripts with escalation notes.

```
$ python demo.py --all

Running 8 events through triage agent...

  harsh_braking_001              Marcus        9/10   COACHING
  speeding_low_002               Sarah         2/10   SELF_REVIEW
  phone_distraction_003          Devon         10/10  IMMEDIATE
  following_close_004            Maria         5/10   COACHING
  drowsy_driving_005             James         8/10   COACHING
  harsh_braking_006              Devon         7/10   COACHING
  shadow_trigger_007             --            --     REJECTED   <- pre-flight
  ambiguous_008                  --            --     REJECTED   <- pre-flight

Summary:
  6 events triaged   (4.4s avg)
  2 rejected by confidence gate (0.09s avg)  <- not LLM calls
  Estimated cost: ~$0.048 for full run
```

The 0.09s on rejected events is not a fast Claude call. It is a pure-Python function that never touches the API. That is intentional.

---

## Why the gate matters

Fleet safety coaching lives or dies on manager trust. If the system flags GPS artifacts, road shadows, or intentional controlled stops as safety violations, managers stop acting on it. At scale, a 5% false positive rate means one out of every 20 coaching conversations is based on noise, and managers notice.

The `confidence_gate` runs four deterministic rules before Claude sees the event. No prompt engineering, no confidence threshold on a model output. Structurally impossible for Claude to skip or override.

```
Rule 1: camera_confidence >= 0.5       (below this: noise, not an event)
Rule 2: gps_variance <= 20.0 meters    (above this: GPS artifact)
Rule 3: speed_mph >= 5.0               (parked or barely rolling: not coaching material)
Rule 4: not (deceleration_g > 0.7 AND speed_mph <= speed_limit_mph AND
             camera_confidence < 0.90) (intentional controlled stop, not harsh braking)
```

Any failure returns `REJECT` in under 0.1s. The LLM loop never starts.

---

## Quick Start

```bash
# Install
pip install -e .

# Set API key
cp .env.example .env.local
# Add your ANTHROPIC_API_KEY to .env.local

# Run single event (streams step-by-step)
python demo.py --event harsh_braking_001

# Watch the gate reject in 0.09s
python demo.py --event shadow_trigger_007

# All 8 events, summary table
python demo.py --all

# Machine-readable output
python demo.py --event harsh_braking_001 --json

# Web UI
uvicorn api.index:app --reload
# Open http://localhost:8000
```

**Python 3.12+ required.** No other system dependencies.

---

## Architecture

```
Safety Event
     |
     v
confidence_gate()              <- pure Python, 0.1s avg -- REJECT false triggers here
     | PROCEED
     v
Claude tool loop (claude-sonnet-4-6, max 8 steps)
  1. get_driver_history()      <- 90-day record, trend direction, prior coaching count
  2. get_event_context()       <- speed, G-force, camera confidence score
  3. get_route_conditions()    <- road type, active hazards, time of day
  4. score_risk()              <- structured Pydantic output, 1-10 scale
     |
     +-- score 1-3  -> create_self_review_prompt()   (driver self-corrects)
     +-- score 4-9  -> generate_coaching_script()    (manager-led session)
     +-- score 10   -> generate_coaching_script()    (immediate intervention)
     |
     v
SSE stream -> FastAPI -> browser or CLI consumer
```

The agent streams `StepEvent` objects as each tool completes, giving real-time visibility into the triage process. The final event is always a `TriageResult` (success) or `RejectionEvent` (gate failure).

---

## Event Routing

| Score | Category | Route | Output |
|-------|----------|-------|--------|
| 1-3 | LOW | `SELF_REVIEW` | 3 reflection questions + video clip prompt |
| 4-6 | MEDIUM | `MANAGER_COACHING` | Concise coaching script, scheduled session |
| 7-9 | HIGH | `MANAGER_COACHING` | Full coaching script + escalation note |
| 10 | CRITICAL | `IMMEDIATE_INTERVENTION` | Urgent script + mandatory supervisor review |
| n/a | n/a | `REJECTED` | Gate failure reason, no API call |

Routing happens inside the `score_risk` tool call. Claude scores the event, returns a structured `RiskScore`, and the agent dispatches to the correct content generator based on the category field. No prompt-level branching.

---

## Design Decisions

### 1. Pre-flight in Python, not a prompt

The confidence gate is a Python function, not a system prompt instruction. Prompt instructions can be reasoned around. A Python guard that runs before the API call is instantiated cannot be.

This pattern costs 0 tokens on every rejection and eliminates an entire class of failure modes.

### 2. Tool-as-schema for structured output

`RiskScore.model_json_schema()` is registered directly as the tool's `input_schema`. Claude is forced to fill in a validated Pydantic model rather than return freeform JSON that gets parsed downstream.

```python
{
    "name": "score_risk",
    "description": "Score risk severity on a 1-10 scale",
    "input_schema": RiskScore.model_json_schema()
}
```

`tool_choice={"type": "auto"}` lets Claude decide when to call it. Once called, Pydantic validates the response at the boundary. No fragile JSON parsing in application code.

### 3. Manual message accumulation

The Anthropic SDK does not automatically maintain conversation state across tool calls. Both the assistant response and the `tool_result` are appended to `messages` manually after each step.

```python
# After each tool call:
messages.append({"role": "assistant", "content": response.content})
messages.append({"role": "user", "content": tool_results})
```

Get this wrong and the model loses context mid-loop. The test `test_message_accumulation_structure` verifies the exact alternating structure after two tool calls.

### 4. SSE streaming with backpressure

The FastAPI route uses `StreamingResponse` with `X-Accel-Buffering: no`. Without that header, Nginx and Vercel buffer the stream until the response completes. The flag disables buffering so step events appear in real time.

Each event is double-newline terminated per the SSE spec:
```python
yield f"data: {json.dumps(event)}\n\n"
```

### 5. Loop termination guard

`MAX_TOOL_STEPS = 8` is a hard ceiling. If the agent loops past it (runaway tool calls, model confusion), the loop raises `AgentLoopError`. This prevents unbounded API spend on a stuck agent. Tested explicitly in `test_loop_termination_guard`.

---

## Test Suite

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

15 tests. No API calls. All mock the Anthropic client.

| Test | What it verifies |
|------|-----------------|
| `test_shadow_trigger_rejected_no_api_call` | Gate rejects, Anthropic never instantiated |
| `test_ambiguous_rejected_no_api_call` | Gate rejects second event type, same guarantee |
| `test_low_risk_routes_to_self_review` | Score 2 produces `SelfReviewPrompt`, no `CoachingScript` |
| `test_critical_risk_routes_to_immediate` | Score 10 produces `IMMEDIATE_INTERVENTION` type |
| `test_message_accumulation_structure` | `messages` array has correct alternating structure after 2 tool calls |
| `test_loop_termination_guard` | `AgentLoopError` raised after `MAX_TOOL_STEPS` |
| + 9 additional routing, SSE format, and gate rule tests | Full path coverage |

All 5 routing paths covered: `REJECTED`, `SELF_REVIEW`, `MANAGER_COACHING`, `IMMEDIATE_INTERVENTION`, error.

---

## Evaluation Framework

[docs/EVALUATION.md](docs/EVALUATION.md) covers the full production evaluation design.

**Tier 1 metrics (manager-facing):**

| Metric | Target |
|--------|--------|
| Manager acceptance rate | >= 80% |
| Recidivism rate (coached drivers) | < 25% |
| False positive rate | < 5% |
| False negative rate (missed HIGH/CRITICAL) | < 3% |

**Tier 2 metrics (system health):**

| Metric | Target |
|--------|--------|
| Gate rejection rate | 10-20% |
| Triage latency (p95) | < 8s |
| Cost per accepted coaching session | < $0.02 |

**The cost case:**

At $0.017 per accepted coaching session vs. $17.50 for a 30-minute manager session, the break-even is less than 1% adoption of coached drivers self-correcting without a manager session. The model does not need to be right 80% of the time to pay for itself.

The evaluation doc also covers: failure taxonomy (7 modes ranked by frequency), A/B test design for personalized vs. generic templates, and the production feedback loop for gate calibration and score drift detection.

---

## Limitations

This is a working demo, not a production deployment. Specific gaps:

- **Driver data is static fixtures.** `get_driver_history()` and `get_event_context()` return hardcoded data from `src/tools/`. Production would call the Samsara API.
- **No auth on the web UI.** The FastAPI route has no authentication. Anyone with the URL can submit events.
- **Cost estimate is an approximation.** `demo.py` calculates cost from token count estimates, not actual API response metadata.
- **Gate thresholds are untested against real fleet data.** The four rules are reasonable starting values. Real calibration requires A/B testing against manager acceptance rates.
- **SSE has no reconnection logic.** The client drops a stream on disconnect and does not resume mid-triage.

---

## Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| API framework | FastAPI + Uvicorn |
| AI model | Claude Sonnet 4.6 (claude-sonnet-4-6) |
| AI SDK | Anthropic Python SDK >= 0.40.0 |
| Schema validation | Pydantic v2 |
| Templates | Jinja2 |
| Testing | pytest, pytest-asyncio, pytest-mock |
| Deployment | Vercel Python runtime |

---

## Project Structure

```
samsara-safety-coaching/
  src/
    agent/
      triage_agent.py        <- Claude tool loop, pre-flight gate, SSE stream
    tools/
      confidence_gate.py     <- Pure-Python pre-flight check (4 rules)
      driver_data.py         <- Static driver history fixtures
      event_data.py          <- Static dashcam event fixtures
    models.py                <- Pydantic models (RiskScore, CoachingScript, etc.)
  api/
    index.py                 <- FastAPI app, SSE route, CORS config
  tests/
    test_triage.py           <- 15 integration tests, all mocked
  docs/
    EVALUATION.md            <- Metrics, failure taxonomy, A/B design, feedback loop
  demo.py                    <- CLI runner with ANSI output and cost estimate
  pyproject.toml             <- Project metadata and dependencies
```

---

## License

MIT
