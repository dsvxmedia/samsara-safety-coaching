# Samsara AI Safety Coaching — Project Instructions

## Project
Autonomous safety coaching agent built as a live demo for a job application to Samsara (AI Engineer role). Triages dashcam safety events, scores risk severity, rejects false triggers without any LLM call, and generates personalized coaching content for managers.

**Target company:** Samsara (fleet telematics)
**Stack:** Python 3.x, Anthropic SDK, click CLI
**Key demo hook:** `confidence_gate` pre-flight check rejects GPS artifacts in 0.09s with zero LLM calls — shows production cost discipline

## Architecture
```
Event input
  ↓
confidence_gate (pure Python, no LLM) → REJECTED if artifact/false trigger
  ↓ passes
triage_agent (Claude) → risk score 1-10 + routing decision
  ↓
SELF_REVIEW (2-4)  →  self-review prompt
COACHING (5-8)     →  manager coaching script
IMMEDIATE (9-10)   →  escalation alert
```

## Key Files
- `src/agent/triage_agent.py` — main Claude agent
- `src/tools/confidence_gate.py` — pre-flight false-trigger rejection
- `src/tools/driver_history.py` — driver risk context
- `src/tools/event_context.py` — event metadata enrichment
- `src/tools/route_context.py` — route/location context
- `src/coaching/` — coaching content generation
- `src/scoring/` — risk scoring logic
- `demo.py` — CLI demo runner

## Reference repos

| Repo | What to take |
|---|---|
| `walkinglabs/learn-harness-engineering` | Harness patterns for multi-agent lifecycle: verification gates, session state, scope control. Apply to LangGraph agent workflow structure. |
| `anthropics/financial-services` | Agent template structure: system prompt + tools + /commands. Mirror for triage_agent.py structure even though domain differs. |
| `The-Swarm-Corporation/AutoHedge` | Multi-agent pipeline pattern: each agent has a focused role, structured JSON output, and passes to next stage. Mirrors confidence_gate → triage_agent → routing. |

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

### General
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Bugs/errors → invoke /investigate
- Code review → invoke /review
- Ship/deploy → invoke /ship
- Save progress → invoke /context-save
- Resume context → invoke /context-restore

### Project-specific
- Agent logic / tool use patterns → invoke /mattpocock-skills:tdd
- Multi-model validation of triage decisions → invoke /llm-council
- Stress-test triage logic or confidence gate thresholds → invoke /grill-with-docs
- Writing coaching output that sounds human → invoke /humanizer-skill
- Final code polish → invoke /impeccable
- README/copy writing → invoke /marketing-skills:copywriting
- Domain modeling (events, risk tiers, routing decisions) → invoke /domain-modeling
- Architecture diagrams → invoke /diagram
- Research fleet safety / telematics trends → invoke /last30days
- Research the codebase → invoke /claude-mem:learn-codebase
- Benchmark triage accuracy or latency → invoke /benchmark-models
- Improve module architecture → invoke /improve-codebase-architecture

### Testing
- Write/run Python tests → invoke /tdd or /mattpocock-skills:tdd
- QA the demo CLI → invoke /qa
