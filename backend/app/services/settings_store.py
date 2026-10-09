from __future__ import annotations

from sqlalchemy.orm import Session

from app import models as m

DEFAULT_WEIGHTS = {
    "response_time": 0.30, "distance": 0.05, "resource_availability": 0.10, "hospital_capacity": 0.15,
    "severity_match": 0.15, "traffic": 0.10, "risk": 0.10, "constraints": 0.05,
}
DEFAULT_CONSTRAINTS = {
    "max_units_per_incident": 30, "min_ambulances_critical": 2, "max_hospital_occupancy_pct": 95,
    "max_response_time_s": 1200, "keep_reserve_per_kind": 1,
}


def _get(db: Session, key: str, default: dict) -> dict:
    row = db.get(m.SystemSetting, key)
    return {**default, **(row.value if row else {})}


def _put(db: Session, key: str, value: dict) -> dict:
    row = db.get(m.SystemSetting, key)
    if row:
        row.value = value
    else:
        db.add(m.SystemSetting(key=key, value=value))
    db.commit()
    return value


def normalize(w: dict) -> dict:
    w = {k: max(0.0, float(w.get(k, 0.0))) for k in DEFAULT_WEIGHTS}
    s = sum(w.values()) or 1.0
    return {k: round(v / s, 4) for k, v in w.items()}


def get_weights(db: Session) -> dict:
    return normalize(_get(db, "decision_weights", DEFAULT_WEIGHTS))


def put_weights(db: Session, w: dict) -> dict:
    return _put(db, "decision_weights", normalize(w))


def get_constraints(db: Session) -> dict:
    return _get(db, "constraints", DEFAULT_CONSTRAINTS)


def put_constraints(db: Session, c: dict) -> dict:
    merged = {**get_constraints(db), **{k: v for k, v in c.items() if k in DEFAULT_CONSTRAINTS and v is not None}}
    return _put(db, "constraints", merged)
