from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafetyEvent:
    event_id: str
    driver_id: str | None
    event_type: str
    timestamp: str
    location: str
    speed_mph: float
    speed_limit_mph: float
    deceleration_g: float | None
    duration_seconds: float | None
    gps_variance: float    # meters — higher = less reliable GPS fix
    camera_confidence: float  # 0–1 — dashcam's own detection confidence
    notes: str


EVENTS: dict[str, SafetyEvent] = {
    "harsh_braking_001": SafetyEvent(
        event_id="harsh_braking_001",
        driver_id="driver_marcus",
        event_type="harsh_braking",
        timestamp="2026-06-17T07:42:11-05:00",
        location="Route 95 N, mile marker 47",
        speed_mph=71.0,
        speed_limit_mph=45.0,
        deceleration_g=0.91,
        duration_seconds=2.4,
        gps_variance=3.1,
        camera_confidence=0.97,
        notes="Wet road, school zone, peak hours. Vehicle slowed 71→28 mph.",
    ),
    "speeding_low_002": SafetyEvent(
        event_id="speeding_low_002",
        driver_id="driver_sarah",
        event_type="speeding",
        timestamp="2026-06-16T14:20:05-05:00",
        location="I-90 E, interchange ramp",
        speed_mph=42.0,
        speed_limit_mph=35.0,
        deceleration_g=None,
        duration_seconds=18.0,
        gps_variance=4.2,
        camera_confidence=0.88,
        notes="7 mph over on a ramp with light traffic. First event in 90 days.",
    ),
    "phone_distraction_003": SafetyEvent(
        event_id="phone_distraction_003",
        driver_id="driver_devon",
        event_type="phone_distraction",
        timestamp="2026-06-17T09:15:33-05:00",
        location="Industrial Blvd, near loading dock",
        speed_mph=38.0,
        speed_limit_mph=35.0,
        deceleration_g=None,
        duration_seconds=12.0,
        gps_variance=5.0,
        camera_confidence=0.96,
        notes="Phone held to ear for 12 seconds at 38 mph. Third phone event this month.",
    ),
    "following_close_004": SafetyEvent(
        event_id="following_close_004",
        driver_id="driver_maria",
        event_type="following_too_close",
        timestamp="2026-06-16T16:55:22-05:00",
        location="Highway 101 S",
        speed_mph=62.0,
        speed_limit_mph=65.0,
        deceleration_g=0.34,
        duration_seconds=8.5,
        gps_variance=3.8,
        camera_confidence=0.91,
        notes="1.2-second following distance at 62 mph. Driver has an improving trend.",
    ),
    "drowsy_driving_005": SafetyEvent(
        event_id="drowsy_driving_005",
        driver_id="driver_james",
        event_type="drowsy_driving",
        timestamp="2026-06-17T05:12:44-05:00",
        location="Highway 280 N",
        speed_mph=55.0,
        speed_limit_mph=65.0,
        deceleration_g=None,
        duration_seconds=6.0,
        gps_variance=4.1,
        camera_confidence=0.89,
        notes="Eye closure detected at 5:12 AM. Veteran driver, single anomaly in 18 months.",
    ),
    "harsh_braking_006": SafetyEvent(
        event_id="harsh_braking_006",
        driver_id="driver_devon",
        event_type="harsh_braking",
        timestamp="2026-06-17T11:30:19-05:00",
        location="Downtown 3rd Ave",
        speed_mph=28.0,
        speed_limit_mph=25.0,
        deceleration_g=0.78,
        duration_seconds=1.9,
        gps_variance=6.2,
        camera_confidence=0.85,
        notes="Third harsh braking event in 30 days. Pattern offender, prior coaching ineffective.",
    ),
    # Adversarial: GPS artifact — parking structure low-speed false trigger
    "shadow_trigger_007": SafetyEvent(
        event_id="shadow_trigger_007",
        driver_id=None,
        event_type="harsh_braking",
        timestamp="2026-06-17T13:04:52-05:00",
        location="Parking structure level 3",
        speed_mph=4.5,
        speed_limit_mph=10.0,
        deceleration_g=0.62,
        duration_seconds=0.8,
        gps_variance=28.4,    # GPS garbage indoors
        camera_confidence=0.41,  # dashcam also unsure
        notes="GPS artifact: indoor parking structure. Low speed, poor GPS fix, low camera confidence.",
    ),
    # Adversarial: conflicting signals — intentional emergency vehicle stop
    "ambiguous_008": SafetyEvent(
        event_id="ambiguous_008",
        driver_id="driver_sarah",
        event_type="harsh_braking",
        timestamp="2026-06-17T08:22:07-05:00",
        location="Emergency vehicle pullover, Oak St",
        speed_mph=31.0,
        speed_limit_mph=35.0,
        deceleration_g=0.81,
        duration_seconds=2.1,
        gps_variance=5.5,
        camera_confidence=0.82,
        notes="Conflicting signals: high G-force but speed below limit — driver yielding to emergency vehicle.",
    ),
}
