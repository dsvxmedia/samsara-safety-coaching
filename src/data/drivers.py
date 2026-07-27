from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class DriverProfile:
    driver_id: str
    name: str
    hire_date: str
    vehicle_class: str
    events_90d: int
    events_30d: int
    coaching_sessions: int
    trend: Literal["IMPROVING", "WORSENING", "STABLE"]
    last_coaching_date: str | None
    notes: str


DRIVERS: dict[str, DriverProfile] = {
    "driver_marcus": DriverProfile(
        driver_id="driver_marcus",
        name="Marcus Johnson",
        hire_date="2023-03-15",
        vehicle_class="Class B",
        events_90d=7,
        events_30d=3,
        coaching_sessions=2,
        trend="WORSENING",
        last_coaching_date="2026-05-01",
        notes="3 harsh braking events in 60 days, trend worsening. Prior coaching has not held.",
    ),
    "driver_sarah": DriverProfile(
        driver_id="driver_sarah",
        name="Sarah Kim",
        hire_date="2025-01-08",
        vehicle_class="Class C",
        events_90d=1,
        events_30d=0,
        coaching_sessions=0,
        trend="STABLE",
        last_coaching_date=None,
        notes="First safety event. New driver with otherwise clean record.",
    ),
    "driver_devon": DriverProfile(
        driver_id="driver_devon",
        name="Devon Richardson",
        hire_date="2022-11-20",
        vehicle_class="Class B",
        events_90d=9,
        events_30d=4,
        coaching_sessions=3,
        trend="WORSENING",
        last_coaching_date="2026-06-01",
        notes="Pattern offender — phone distraction + harsh braking repeating. Three coaching sessions, none effective.",
    ),
    "driver_maria": DriverProfile(
        driver_id="driver_maria",
        name="Maria Lozano",
        hire_date="2023-07-10",
        vehicle_class="Class C",
        events_90d=3,
        events_30d=1,
        coaching_sessions=2,
        trend="IMPROVING",
        last_coaching_date="2026-04-15",
        notes="Was high-risk 90 days ago. Coaching has held. Significant improving trend.",
    ),
    "driver_james": DriverProfile(
        driver_id="driver_james",
        name="James Torres",
        hire_date="2019-06-05",
        vehicle_class="Class A",
        events_90d=1,
        events_30d=1,
        coaching_sessions=1,
        trend="STABLE",
        last_coaching_date="2024-11-20",
        notes="Veteran driver. 18-month clean record before this event. Single anomaly.",
    ),
}
