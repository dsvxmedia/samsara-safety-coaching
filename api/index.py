"""
FastAPI application — Vercel Python runtime entrypoint.

Endpoints:
  GET  /              → event queue dashboard (Jinja2)
  GET  /event/{id}    → event detail page
  GET  /driver/{id}   → driver 90-day profile
  POST /api/triage    → SSE stream of agent steps
  GET  /api/events    → JSON list of all events
  GET  /health        → liveness check
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections import defaultdict
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv(".env.local")
load_dotenv(".env")

from src.agent.triage_agent import AgentLoopError, run_triage
from src.data.drivers import DRIVERS
from src.data.events import EVENTS
from src.models import RejectionEvent, StepEvent, TriageResult
from src.tools.confidence_gate import confidence_gate

app = FastAPI(title="Samsara Safety Coaching Automator", version="0.1.0")

# Templates and static files
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(_BASE, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(_BASE, "static")), name="static")

# In-memory rate limiter: 20 requests per hour per IP
_rate_buckets: dict[str, list[float]] = defaultdict(list)
DEMO_TOKEN = os.environ.get("DEMO_TOKEN", "samsara-demo-2026")
RATE_LIMIT = 20


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    window = [t for t in _rate_buckets[client_ip] if now - t < 3600]
    _rate_buckets[client_ip] = window
    if len(window) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: {RATE_LIMIT} requests/hour. Use the CLI for unrestricted access.",
        )
    _rate_buckets[client_ip].append(now)


def _check_demo_token(x_demo_token: str | None) -> None:
    if x_demo_token != DEMO_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid X-Demo-Token header. Set DEMO_TOKEN in .env.local.",
        )


# ── Web UI routes ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    events = []
    rejected_count = 0
    for event_id, event in EVENTS.items():
        driver = DRIVERS.get(event.driver_id or "") if event.driver_id else None
        gate = confidence_gate(event)
        if gate.decision == "REJECT":
            rejected_count += 1
        events.append({
            "event_id": event_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "location": event.location,
            "driver_name": driver.name if driver else "Unknown",
            "driver_id": event.driver_id,
            "gate_decision": gate.decision,
        })
    total = len(events)
    stats = {
        "total": total,
        "triaged": total - rejected_count,
        "rejected": rejected_count,
        "rejection_pct": round(rejected_count / total * 100) if total else 0,
    }
    return templates.TemplateResponse(request, "index.html", {"events": events, "stats": stats})


@app.get("/event/{event_id}", response_class=HTMLResponse)
async def event_detail(request: Request, event_id: str) -> HTMLResponse:
    event = EVENTS.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    driver = DRIVERS.get(event.driver_id or "") if event.driver_id else None

    event_ids = list(EVENTS.keys())
    idx = event_ids.index(event_id)
    prev_id = event_ids[idx - 1] if idx > 0 else None
    next_id = event_ids[idx + 1] if idx < len(event_ids) - 1 else None

    return templates.TemplateResponse(request, "event.html", {
        "event": {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "location": event.location,
            "speed_mph": event.speed_mph,
            "speed_limit_mph": event.speed_limit_mph,
            "deceleration_g": event.deceleration_g,
            "camera_confidence": event.camera_confidence,
            "notes": event.notes,
        },
        "driver": {
            "driver_id": driver.driver_id if driver else None,
            "name": driver.name if driver else "Unknown",
            "trend": driver.trend if driver else "—",
        } if driver else None,
        "prev_event_id": prev_id,
        "next_event_id": next_id,
        "event_index": idx + 1,
        "event_total": len(event_ids),
    })


@app.get("/driver/{driver_id}", response_class=HTMLResponse)
async def driver_profile(request: Request, driver_id: str) -> HTMLResponse:
    driver = DRIVERS.get(driver_id)
    if driver is None:
        raise HTTPException(status_code=404, detail="Driver not found")
    driver_events = [
        {"event_id": eid, **{k: v for k, v in vars(e).items()}}
        for eid, e in EVENTS.items()
        if e.driver_id == driver_id
    ]
    return templates.TemplateResponse(request, "driver.html", {
        "driver": {
            "driver_id": driver.driver_id,
            "name": driver.name,
            "hire_date": driver.hire_date,
            "vehicle_class": driver.vehicle_class,
            "events_90d": driver.events_90d,
            "events_30d": driver.events_30d,
            "coaching_sessions": driver.coaching_sessions,
            "trend": driver.trend,
            "last_coaching_date": driver.last_coaching_date,
            "notes": driver.notes,
        },
        "events": driver_events,
    })


# ── API routes ────────────────────────────────────────────────────────────────

@app.post("/api/triage")
async def triage_event(
    request: Request,
    x_demo_token: str | None = Header(default=None, alias="X-Demo-Token"),
) -> StreamingResponse:
    """SSE stream: yields agent steps then a done event."""
    _check_demo_token(x_demo_token)
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    body = await request.json()
    event_id = body.get("event_id", "")
    if not event_id or event_id not in EVENTS:
        raise HTTPException(status_code=400, detail=f"Unknown event_id: {event_id!r}")

    async def generate():
        # run_triage is a sync generator that makes blocking Anthropic API calls.
        # Running it directly in an async generator blocks the event loop, so all
        # SSE data arrives at once after completion. Fix: producer thread + queue.
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def producer() -> None:
            try:
                for item in run_triage(event_id):
                    asyncio.run_coroutine_threadsafe(queue.put(item), loop)
            except AgentLoopError as exc:
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop)
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        threading.Thread(target=producer, daemon=True).start()

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, AgentLoopError):
                yield f"data: {json.dumps({'type': 'error', 'message': str(item)})}\n\n"
                break
            if isinstance(item, Exception):
                yield f"data: {json.dumps({'type': 'error', 'message': f'Internal error: {type(item).__name__}'})}\n\n"
                break
            if isinstance(item, (StepEvent, RejectionEvent, TriageResult)):
                yield f"data: {item.model_dump_json()}\n\n"

        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",  # required for Vercel SSE
            "Cache-Control": "no-cache",
        },
    )


@app.get("/api/stats")
async def api_stats() -> JSONResponse:
    total = len(EVENTS)
    rejected = sum(1 for e in EVENTS.values() if confidence_gate(e).decision == "REJECT")
    return JSONResponse({
        "total": total,
        "triaged": total - rejected,
        "rejected": rejected,
        "rejection_pct": round(rejected / total * 100) if total else 0,
        "est_cost_per_session_usd": 0.017,
    })


@app.get("/api/events")
async def list_events() -> JSONResponse:
    return JSONResponse({
        event_id: {
            "event_id": event.event_id,
            "driver_id": event.driver_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "location": event.location,
            "speed_mph": event.speed_mph,
            "speed_limit_mph": event.speed_limit_mph,
        }
        for event_id, event in EVENTS.items()
    })


@app.get("/health")
async def health() -> JSONResponse:
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return JSONResponse({"status": "ok", "api_key_configured": has_key})
