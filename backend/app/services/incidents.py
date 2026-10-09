from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.services import graph_service
from app.services import serializers as ser
from app.services.bus import bus
from app.services.city_data import GAZETTEER, LOCATION_ALIASES
from app.services.events import log_event
from app.toc import fsm


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra


def next_incident_id(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"INC-{year}-"
    ids = db.scalars(select(m.Incident.id).where(m.Incident.id.like(prefix + "%"))).all()
    n = max((int(i.rsplit("-", 1)[1]) for i in ids if i.rsplit("-", 1)[1].isdigit()), default=0) + 1
    return f"{prefix}{n:04d}"


def resolve_place(name: str) -> tuple[str, float, float, str] | None:
    key = name.strip().upper().replace(" ", "_").replace("-", "_")
    if key in GAZETTEER:
        return GAZETTEER[key]
    alias = LOCATION_ALIASES.get(name.strip().lower())
    if alias:
        return GAZETTEER[alias]
    for k, (disp, lat, lon, typ) in GAZETTEER.items():
        if name.strip().lower() in disp.lower():
            return disp, lat, lon, typ
    return None


def create_incident(db: Session, data: dict, *, command_text: str | None = None, severity_source: str = "USER") -> m.Incident:
    lat, lon = data.get("lat"), data.get("lon")
    loc_name = data.get("location_name") or ""
    if lat is None or lon is None:
        place = resolve_place(loc_name) if loc_name else None
        if place is None:
            raise DomainError("UNKNOWN_LOCATION", f"Could not resolve location '{loc_name}'. Provide latitude/longitude.", 422)
        _, lat, lon, _ = place
    if not (22.55 <= lat <= 22.90 and 75.70 <= lon <= 76.05):
        raise DomainError("OUT_OF_AREA", "Coordinates are outside the simulated Indore service area", 422)
    g = graph_service.get_graph(db)
    inc = m.Incident(
        id=next_incident_id(db), type=data["type"],
        title=data.get("title") or f"{data['type'].replace('_', ' ').title()} at {loc_name or 'unknown location'}",
        location_name=loc_name, lat=lat, lon=lon, node_id=g.nearest_node(lat, lon),
        people_affected=int(data.get("people_affected") or 0),
        severity=data.get("severity_estimate") or data.get("severity") or "MEDIUM",
        severity_source=severity_source if (data.get("severity_estimate") or data.get("severity")) else "RULE_BASED",
        state=fsm.INITIAL, status="ACTIVE", description=data.get("description") or "",
        exits_available=data.get("exits_available"), exits_blocked=data.get("exits_blocked"),
        hazards=data.get("hazards") or [], additional_info=data.get("additional_info") or "",
        command_text=command_text, requirement=data.get("requirement") or {},
    )
    if data.get("detected_at"):
        inc.detected_at = data["detected_at"]
    db.add(inc)
    db.flush()
    db.add(m.StateTransition(incident_id=inc.id, from_state=None, to_state=fsm.INITIAL, event="create",
                             reason="Incident reported"))
    log_event(db, "INCIDENT_DETECTED", f"{inc.title} ({inc.people_affected} affected)", inc.id,
              None, fsm.INITIAL, commit=False, payload={"lat": lat, "lon": lon, "type": inc.type})
    db.commit()
    bus.publish("incident_created", ser.incident(inc), inc.id)
    return inc


def get_incident(db: Session, incident_id: str) -> m.Incident:
    inc = db.get(m.Incident, incident_id)
    if inc is None:
        raise DomainError("NOT_FOUND", f"Incident {incident_id} not found", 404)
    return inc


def transition(db: Session, inc: m.Incident, to_state: str, reason: str = "", event: str | None = None,
               commit: bool = True) -> str:
    """Apply δ(state, event). Raises DomainError if the DFA has no such transition."""
    prev = inc.state
    try:
        ev = event or fsm.event_for(prev, to_state)
        new = fsm.step(prev, ev)
    except fsm.InvalidTransition as e:
        raise DomainError("INVALID_TRANSITION", str(e), 409, allowed_next=fsm.allowed_next(prev)) from None
    inc.state = new
    if new == "RESOLVED":
        inc.status = "RESOLVED"
        inc.resolved_at = datetime.now(timezone.utc)
    elif new == "CANCELLED":
        inc.status = "CANCELLED"
        inc.resolved_at = datetime.now(timezone.utc)
    db.add(m.StateTransition(incident_id=inc.id, from_state=prev, to_state=new, event=ev, reason=reason))
    log_event(db, "STATE_CHANGE", f"{prev} → {new} ({ev})" + (f": {reason}" if reason else ""), inc.id, prev, new,
              commit=False)
    if commit:
        db.commit()
    bus.publish("state_change", {"from_state": prev, "to_state": new, "event": ev, "reason": reason}, inc.id)
    return new


def advance_along_main_path(db: Session, inc: m.Incident, target: str, reason: str = "") -> None:
    path = fsm.main_path()
    if inc.state not in path or target not in path:
        transition(db, inc, target, reason)
        return
    while path.index(inc.state) < path.index(target):
        transition(db, inc, path[path.index(inc.state) + 1], reason, commit=False)
    db.commit()


def list_incidents(db: Session, status=None, type_=None, severity=None, q=None, limit=200) -> list[m.Incident]:
    stmt = select(m.Incident).order_by(m.Incident.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(m.Incident.status == status)
    if type_:
        stmt = stmt.where(m.Incident.type == type_)
    if severity:
        stmt = stmt.where(m.Incident.severity == severity)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(m.Incident.id.ilike(like) | m.Incident.title.ilike(like) | m.Incident.location_name.ilike(like)
                          | m.Incident.description.ilike(like))
    return list(db.scalars(stmt))


def count_active(db: Session) -> tuple[int, int]:
    active = db.scalar(select(func.count()).select_from(m.Incident).where(m.Incident.status == "ACTIVE")) or 0
    critical = db.scalar(select(func.count()).select_from(m.Incident).where(
        m.Incident.status == "ACTIVE", m.Incident.severity == "CRITICAL")) or 0
    return active, critical
