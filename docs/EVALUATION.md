# Evaluation Framework

This document describes how I would measure, stress-test, and iterate on the Safety Coaching Automator if it were shipping to production.

---

## Proposed Metrics

### Tier 1 — Outcome metrics (what actually matters)

| Metric | Definition | Target |
|--------|-----------|--------|
| **Manager acceptance rate** | % of generated coaching scripts reviewed and sent (not discarded) by managers | ≥ 80% |
| **Recidivism rate** | % of coached drivers with another event in 30 days | < 25% vs. no-coaching baseline |
| **False positive rate** | % of REJECTED events that a human reviewer would have coached on | < 5% |
| **False negative rate** | % of PROCEED events that a human reviewer would have rejected | < 3% |

### Tier 2 — Operational metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| **Gate rejection rate** | % of events rejected by confidence_gate | 10–20% (too high = gate too aggressive) |
| **Triage latency** | End-to-end time for a PROCEED event | < 8s p95 |
| **Cost per triage** | Anthropic API cost per successfully routed event | < $0.02 |
| **Tool loop depth** | Avg number of tool calls per triage | ≤ 6 (8 = near limit) |

### Tier 3 — Model quality metrics

| Metric | How to measure |
|--------|---------------|
| **Score calibration** | Human-labeled severity vs. model score — Spearman correlation target ≥ 0.85 |
| **Tone accuracy** | Does tone match driver trend? (WORSENING → firm, IMPROVING → affirming) |
| **Specificity** | Does script reference actual event details vs. generic language? (GPT-4o judge, 0–5 scale) |

---

## Failure Taxonomy

Based on the agent design, these are the expected failure modes ranked by frequency:

| # | Failure | Root Cause | Detection | Mitigation |
|---|---------|-----------|-----------|------------|
| 1 | False gate rejection (valid event rejected) | Rule thresholds too aggressive | Human review queue for REJECTEDs | Tune thresholds from review data |
| 2 | Score miscalibration | Incomplete context at scoring step | Human label vs. model score comparison | Prompt + few-shot examples |
| 3 | Generic coaching language | Claude ignores specific event details | GPT-4o judge on specificity | Stronger prompt, examples in system prompt |
| 4 | Wrong tone for driver trend | Driver history not surfaced clearly | Manual spot-check | Few-shot tone examples |
| 5 | Tool loop exceeding 8 steps | Claude calls context tools redundantly | AgentLoopError raised, logged | Prompt tightening, max_steps guard already in place |
| 6 | False gate proceed (noise event triaged) | New artifact pattern not covered by rules | Manager discards script, marks as noise | Feedback loop → gate rule addition |
| 7 | SSE stream dropout | Vercel cold start + long agent run | Health endpoint + stream keepalive | maxDuration: 60 already configured |

---

## A/B Test Design

**Question:** Does personalized coaching (with driver history + route context) outperform a generic coaching template?

**Design:**
- Control: generic template filled from event metadata only (event type, timestamp, location)
- Treatment: full agent pipeline (driver history + event context + route conditions → Pydantic score → personalized script)
- Assignment: random per driver per week (not per event — same driver should get consistent experience)
- Primary outcome: manager acceptance rate (did they send the script?)
- Secondary outcome: 30-day recidivism rate

**Minimum detectable effect:** 10pp improvement in acceptance rate (from ~60% baseline to ~70%)
**Sample size estimate:** ~200 coached drivers per arm (~4 weeks at typical fleet volume)

**Guard rails:**
- Don't A/B test IMMEDIATE_INTERVENTION events — always use full pipeline
- Exclude drivers with < 3 weeks in fleet (insufficient history baseline)

---

## Production Feedback Loop

The current demo has no feedback loop. In production:

1. **Manager action signal**: track whether each script was sent, edited, or discarded
2. **Discard reason**: optional 1-click reason (too generic / wrong tone / event was already resolved)
3. **Gate calibration**: flag REJECTED events for weekly human review — any human "would have coached this" vote feeds back into gate threshold tuning
4. **Score drift detection**: if model score distribution shifts (e.g., month-over-month more HIGH events), investigate whether it's real behavior change or prompt drift
5. **Cost monitoring**: cost per triage logged to Vercel logs; alert if > $0.05 (3× current target)

---

## Known Limitations of This Demo

| Limitation | Production fix |
|-----------|---------------|
| Synthetic event data | Samsara API integration for real dashcam event stream |
| No real CV/ML pipeline | Samsara's actual event detection scores would replace camera_confidence |
| In-memory rate limit | Redis-backed rate limiting per fleet account |
| No audit log persistence | Write TriageResult to Postgres/Neon per event |
| Single-region Vercel deployment | Vercel Fluid Compute multi-region failover |
| No driver notification | Integrate with Samsara driver app API for self-review delivery |

---

## Cost Estimate (claude-sonnet-4-6, June 2026 pricing)

Per 8-event demo run:
- 6 triaged events × ~2,000 input tokens × $3.00/MTok = $0.036
- 6 triaged events × ~500 output tokens × $15.00/MTok = $0.045
- **Total: ~$0.08 per full run**

Per production event at scale (1,000 events/day):
- ~$13.50/day in API costs
- At 80% acceptance rate: $13.50 / 800 accepted scripts = **$0.017 per accepted coaching session**

Compare to: a 30-minute manager coaching session at $35/hr loaded cost = $17.50. The agent delivers a personalized script for under 2 cents.
