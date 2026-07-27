from __future__ import annotations

# Synthetic route data keyed by event_id.
# In production this would query Samsara's map/route API.
_ROUTE_DATA: dict[str, dict] = {
    "harsh_braking_001": {
        "road_type": "arterial",
        "zone": "school_zone",
        "posted_speed_limit": 45,
        "time_of_day": "peak_morning",
        "conditions": ["wet_road", "school_zone_active"],
        "known_hazard_reports": 3,
        "description": "School zone on Route 95 N with 3 prior incident reports. Active during peak drop-off hours.",
    },
    "speeding_low_002": {
        "road_type": "highway_ramp",
        "zone": "general",
        "posted_speed_limit": 35,
        "time_of_day": "afternoon",
        "conditions": ["light_traffic", "dry_road"],
        "known_hazard_reports": 0,
        "description": "Standard highway interchange ramp. Light afternoon traffic, no hazard history.",
    },
    "phone_distraction_003": {
        "road_type": "industrial",
        "zone": "loading_dock_area",
        "posted_speed_limit": 35,
        "time_of_day": "morning",
        "conditions": ["heavy_truck_traffic", "pedestrian_workers"],
        "known_hazard_reports": 1,
        "description": "Industrial boulevard near active loading dock. High pedestrian worker exposure.",
    },
    "following_close_004": {
        "road_type": "highway",
        "zone": "general",
        "posted_speed_limit": 65,
        "time_of_day": "afternoon_rush",
        "conditions": ["moderate_traffic", "dry_road"],
        "known_hazard_reports": 0,
        "description": "Highway 101 S during afternoon commute. Standard highway following-distance risk.",
    },
    "drowsy_driving_005": {
        "road_type": "highway",
        "zone": "general",
        "posted_speed_limit": 65,
        "time_of_day": "early_morning",
        "conditions": ["very_light_traffic", "pre_dawn"],
        "known_hazard_reports": 0,
        "description": "Highway 280 N at 5 AM. Pre-dawn conditions amplify drowsiness risk significantly.",
    },
    "harsh_braking_006": {
        "road_type": "urban_arterial",
        "zone": "downtown",
        "posted_speed_limit": 25,
        "time_of_day": "midday",
        "conditions": ["pedestrian_crossing", "mixed_traffic"],
        "known_hazard_reports": 2,
        "description": "Downtown 3rd Ave with active pedestrian crossings. Two prior incident reports.",
    },
    "shadow_trigger_007": {
        "road_type": "parking_structure",
        "zone": "private_property",
        "posted_speed_limit": 10,
        "time_of_day": "afternoon",
        "conditions": ["indoor", "gps_unreliable"],
        "known_hazard_reports": 0,
        "description": "Indoor parking structure. GPS unreliable. Event likely a sensor artifact.",
    },
    "ambiguous_008": {
        "road_type": "urban_arterial",
        "zone": "general",
        "posted_speed_limit": 35,
        "time_of_day": "morning",
        "conditions": ["dry_road", "emergency_vehicle_nearby"],
        "known_hazard_reports": 0,
        "description": "Oak St residential area. Emergency vehicle active nearby at time of event.",
    },
}


def get_route_conditions(event_id: str) -> dict:
    """Return road type, conditions, and hazard context for the given event."""
    data = _ROUTE_DATA.get(event_id)
    if data is None:
        return {
            "found": False,
            "event_id": event_id,
            "error": "Route data not available for this event",
        }
    return {"found": True, "event_id": event_id, **data}
