"""ORM → API dict converters (single place so every endpoint returns identical shapes)."""
from __future__ import annotations

from datetime import datetime, timezone

from app import models as m


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def incident(i: m.Incident) -> dict:
    return {
        "id": i.id, "type": i.type, "title": i.title, "location_name": i.location_name, "lat": i.lat, "lon": i.lon,
        "node_id": i.node_id, "people_affected": i.people_affected, "severity": i.severity,
        "severity_source": i.severity_source, "state": i.state, "status": i.status, "description": i.description,
        "exits_available": i.exits_available, "exits_blocked": i.exits_blocked, "hazards": i.hazards or [],
        "detected_at": iso(i.detected_at), "created_at": iso(i.created_at), "resolved_at": iso(i.resolved_at),
        "response_time_s": i.response_time_s, "additional_info": i.additional_info, "command_text": i.command_text,
        "requirement": i.requirement or {}, "hospital_id": i.hospital_id,
    }


def event(e: m.IncidentEvent) -> dict:
    return {"id": e.id, "timestamp": iso(e.timestamp), "incident_id": e.incident_id, "event_type": e.event_type,
            "previous_state": e.previous_state, "new_state": e.new_state, "action": e.action,
            "decision": e.decision, "confidence": e.confidence, "payload": e.payload or {}}


def resource(r: m.Resource) -> dict:
    lat = r.location.lat if r.location else r.home_lat
    lon = r.location.lon if r.location else r.home_lon
    return {"id": r.id, "code": r.code, "kind": r.kind, "status": r.status, "lat": lat, "lon": lon,
            "station": r.station, "capacity": r.capacity, "equipment": r.equipment or [],
            "assigned_incident_id": r.assigned_incident_id, "eta_s": r.eta_s, "speed_kmh": r.speed_kmh,
            "destination": r.destination, "heading": r.location.heading if r.location else 0.0}


def load_status(pct: float) -> str:
    if pct >= 95:
        return "CRITICAL"
    if pct >= 80:
        return "HIGH"
    if pct >= 55:
        return "MODERATE"
    return "LOW"


def hospital(h: m.Hospital) -> dict:
    c = h.capacity
    er_av = max(0, c.emergency_beds_total - c.emergency_beds_occupied)
    icu_av = max(0, c.icu_total - c.icu_occupied)
    pct = 100.0 * c.emergency_beds_occupied / c.emergency_beds_total if c.emergency_beds_total else 100.0
    return {"id": h.id, "code": h.code, "name": h.name, "lat": h.lat, "lon": h.lon, "node_id": h.node_id,
            "emergency_beds_total": c.emergency_beds_total, "emergency_beds_occupied": c.emergency_beds_occupied,
            "emergency_beds_available": er_av, "icu_total": c.icu_total, "icu_occupied": c.icu_occupied,
            "icu_available": icu_av, "occupancy_pct": round(pct, 1), "specializations": h.specializations or [],
            "load_status": load_status(pct), "updated_at": iso(c.updated_at)}


def prediction(p: m.Prediction) -> dict:
    return {"id": p.id, "model_name": p.model_name, "model_version": p.model_version, "source": p.source,
            "features": p.features, "prediction": (p.prediction or {}).get("value"), "probabilities": p.probabilities,
            "confidence": p.confidence, "created_at": iso(p.created_at), "incident_id": p.incident_id}


def route(r: m.Route) -> dict:
    return {"id": r.id, "incident_id": r.incident_id, "purpose": r.purpose, "algorithm": r.algorithm, "path": r.path,
            "geometry": r.geometry, "distance_m": r.distance_m, "travel_time_s": r.travel_time_s,
            "nodes_expanded": r.nodes_expanded, "label": r.label, "found": True, "created_at": iso(r.created_at)}


def user(u: m.User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "full_name": u.full_name, "active": u.active,
            "created_at": iso(u.created_at)}
