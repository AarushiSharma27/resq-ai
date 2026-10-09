from __future__ import annotations

from sqlalchemy.orm import Session

from app import models as m
from app.services import serializers as ser
from app.services.bus import bus


def log_event(db: Session, event_type: str, action: str, incident_id: str | None = None,
              previous_state: str | None = None, new_state: str | None = None, decision: str | None = None,
              confidence: float | None = None, payload: dict | None = None, commit: bool = True) -> m.IncidentEvent:
    """Persist an event to the audit trail and push it to WebSocket subscribers."""
    ev = m.IncidentEvent(incident_id=incident_id, event_type=event_type, action=action, previous_state=previous_state,
                         new_state=new_state, decision=decision, confidence=confidence, payload=payload or {})
    db.add(ev)
    if commit:
        db.commit()
    else:
        db.flush()
    bus.publish("event", ser.event(ev), incident_id)
    return ev
