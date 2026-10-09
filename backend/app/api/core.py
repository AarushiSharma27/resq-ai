"""Auth, system, incidents, pipeline, compiler and theory-of-computation endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.compiler import SemanticContext, compile_command, grammar_info, parse, regex_accepts, tokenize
from app.config import get_settings
from app.database import get_db
from app.security import create_token, current_user, hash_password, require, verify_password
from app.services import decision as decision_svc
from app.services import graph_service, hospitals, incidents, pipeline, resources
from app.services import serializers as ser
from app.toc import fsm, state_space

router = APIRouter(prefix="/api")
IncidentType = Literal["FIRE", "ACCIDENT", "MEDICAL", "FLOOD", "EARTHQUAKE", "CHEMICAL_HAZARD", "CRIME",
                       "MISSING_PERSON", "OTHER"]
Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
operator = require("OPERATOR")


# ------------------------------------------------------------------ auth / system
class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(m.User).where(m.User.username == body.username))
    if u is None or not u.active or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, detail={"code": "BAD_CREDENTIALS", "message": "Invalid username or password"})
    return {"access_token": create_token(u), "token_type": "bearer", "user": ser.user(u)}


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(default="", max_length=128)


@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    # Self-registered accounts get OPERATOR; only seeded/admin-managed accounts hold ADMIN.
    if db.scalar(select(m.User).where(m.User.username == body.username)) is not None:
        raise HTTPException(409, detail={"code": "USERNAME_TAKEN", "message": "That username is already taken"})
    u = m.User(username=body.username, password_hash=hash_password(body.password), role="OPERATOR",
               full_name=body.full_name.strip())
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"access_token": create_token(u), "token_type": "bearer", "user": ser.user(u)}


@router.get("/auth/me")
def me(user: m.User = Depends(current_user)):
    return ser.user(user)


@router.get("/health")
def health():
    s = get_settings()
    live = s.data_mode == "LIVE"
    return {"status": "ok", "mode": s.data_mode, "version": s.version,
            "data_sources": {"traffic": "LIVE" if live else "SIMULATED", "weather": "LIVE" if s.weather_api_key else "SIMULATED",
                             "hospitals": "LIVE" if s.hospital_api_url else "SIMULATED", "map": "OPENSTREETMAP"},
            "database": "sqlite" if s.is_sqlite else "postgresql"}


@router.get("/dashboard/summary")
def dashboard(db: Session = Depends(get_db), _=Depends(current_user)):
    active, critical = incidents.count_active(db)
    hs = [ser.hospital(h) for h in db.scalars(select(m.Hospital))]
    times = [t for t in db.scalars(select(m.Incident.response_time_s).where(m.Incident.response_time_s.is_not(None)))]
    return {"active_incidents": active, "critical_incidents": critical,
            "available": resources.available_counts(db), "totals": resources.total_counts(db),
            "hospital_beds_available": sum(h["emergency_beds_available"] for h in hs),
            "icu_beds_available": sum(h["icu_available"] for h in hs),
            "avg_response_time_s": round(sum(times) / len(times), 1) if times else None,
            "traffic_level": decision_svc.traffic_overall(graph_service.get_graph(db)),
            "mode": get_settings().data_mode}


# ------------------------------------------------------------------ incidents
class IncidentIn(BaseModel):
    type: IncidentType
    location_name: str = ""
    lat: float | None = None
    lon: float | None = None
    people_affected: int = Field(0, ge=0)
    severity_estimate: Severity | None = None
    description: str | None = None
    exits_available: int | None = Field(None, ge=0)
    exits_blocked: int | None = Field(None, ge=0)
    hazards: list[str] = []
    detected_at: datetime | None = None
    additional_info: str | None = None


@router.post("/incidents")
def create_incident(body: IncidentIn, db: Session = Depends(get_db), _=Depends(operator)):
    return ser.incident(incidents.create_incident(db, body.model_dump()))


@router.get("/incidents")
def list_incidents(status: str | None = None, type: str | None = None, severity: str | None = None,
                   q: str | None = None, limit: int = 200, db: Session = Depends(get_db), _=Depends(current_user)):
    return [ser.incident(i) for i in incidents.list_incidents(db, status, type, severity, q, limit)]


@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: str, db: Session = Depends(get_db), _=Depends(current_user)):
    inc = incidents.get_incident(db, incident_id)
    cmd = db.scalar(select(m.CompilerCommand).where(m.CompilerCommand.incident_id == inc.id)
                    .order_by(m.CompilerCommand.id.desc()))
    route = db.scalar(select(m.Route).where(m.Route.incident_id == inc.id).order_by(m.Route.id.desc()))
    dec = db.scalar(select(m.Decision).where(m.Decision.incident_id == inc.id).order_by(m.Decision.id.desc()))
    units = db.scalars(select(m.Resource).where(m.Resource.assigned_incident_id == inc.id))
    runs = db.scalars(select(m.SimulationRun).where(m.SimulationRun.incident_id == inc.id)
                      .order_by(m.SimulationRun.started_at.desc()))
    evs = db.scalars(select(m.IncidentEvent).where(m.IncidentEvent.incident_id == inc.id)
                     .order_by(m.IncidentEvent.timestamp.desc()).limit(200))
    hosp = db.get(m.Hospital, inc.hospital_id) if inc.hospital_id else None
    status = pipeline.fsm_status(db, inc)
    return {"incident": ser.incident(inc), "compilation": cmd.result if cmd else None,
            "predictions": [ser.prediction(p) for p in decision_svc.inc_predictions(db, inc.id)],
            "state_history": status["history"], "fsm": status,
            "allocations": [{"resource_id": r.id, "code": r.code, "kind": r.kind, "status": r.status, "eta_s": r.eta_s}
                            for r in units],
            "route": ser.route(route) if route else None, "hospital": ser.hospital(hosp) if hosp else None,
            "decision": {k: v for k, v in dec.data.items() if k != "hospital_ranking"} if dec else None,
            "simulation_runs": [_run_summary(r) for r in runs], "events": [ser.event(e) for e in evs]}


def _run_summary(r: m.SimulationRun) -> dict:
    return {"run_id": r.id, "incident_id": r.incident_id, "status": r.status, "speed": r.speed,
            "started_at": ser.iso(r.started_at), "finished_at": ser.iso(r.finished_at), "metrics": r.metrics}


class TransitionIn(BaseModel):
    to_state: str
    reason: str = ""


@router.post("/incidents/{incident_id}/transition")
def transition(incident_id: str, body: TransitionIn, db: Session = Depends(get_db), _=Depends(operator)):
    inc = incidents.get_incident(db, incident_id)
    prev = inc.state
    incidents.transition(db, inc, body.to_state, body.reason or "Manual transition")
    if inc.status != "ACTIVE":
        resources.release(db, inc.id)
    return {"ok": True, "current": inc.state, "previous": prev, "allowed_next": fsm.allowed_next(inc.state)}


def _close(db: Session, incident_id: str, target: str) -> dict:
    inc = incidents.get_incident(db, incident_id)
    if inc.status != "ACTIVE":
        raise incidents.DomainError("ALREADY_CLOSED", f"Incident is already {inc.status}", 409)
    if target == "RESOLVED" and inc.state != "ACTIVE_RESPONSE":
        incidents.advance_along_main_path(db, inc, "ACTIVE_RESPONSE", "Fast-forwarded by operator")
    incidents.transition(db, inc, target, "Closed by operator")
    resources.release(db, inc.id)
    return ser.incident(inc)


@router.post("/incidents/{incident_id}/resolve")
def resolve(incident_id: str, db: Session = Depends(get_db), _=Depends(operator)):
    return _close(db, incident_id, "RESOLVED")


@router.post("/incidents/{incident_id}/cancel")
def cancel(incident_id: str, db: Session = Depends(get_db), _=Depends(operator)):
    return _close(db, incident_id, "CANCELLED")


# ------------------------------------------------------------------ pipeline
class PipelineIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    incident_id: str | None = None
    overrides: dict[str, Any] | None = None
    auto_simulate: bool = False
    speed: Literal[1, 2, 5, 10] = 5


@router.post("/pipeline/run")
def run_pipeline(body: PipelineIn, db: Session = Depends(get_db), _=Depends(operator)):
    return pipeline.run(db, body.text, body.overrides, body.auto_simulate, body.speed, body.incident_id)


# ------------------------------------------------------------------ compiler
class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    overrides: dict[str, Any] | None = None


@router.get("/compiler/grammar")
def grammar(_=Depends(current_user)):
    return grammar_info()


@router.post("/compiler/lex")
def lex(body: TextIn, _=Depends(current_user)):
    toks, errs = tokenize(body.text)
    return {"tokens": [t.dict() for t in toks], "errors": errs}


@router.post("/compiler/parse")
def parse_ep(body: TextIn, _=Depends(current_user)):
    toks, _errs = tokenize(body.text)
    tree, errors = parse(toks)
    return {"valid": tree is not None, "tokens": [t.dict() for t in toks], "tree": tree.to_dict() if tree else None,
            "errors": errors}


def _compile(db: Session, body: TextIn) -> dict:
    ctx: SemanticContext = pipeline.semantic_context(db)
    return compile_command(body.text, ctx, body.overrides)


@router.post("/compiler/validate")
def validate(body: TextIn, db: Session = Depends(get_db), _=Depends(current_user)):
    r = _compile(db, body)
    sem = r["semantic"] or {}
    return {"valid": r["valid"], "errors": r["parse"]["errors"] + sem.get("errors", []),
            "warnings": r["lex_warnings"] + sem.get("warnings", []), "ir": r["ir"]}


@router.post("/compiler/compile")
def compile_ep(body: TextIn, db: Session = Depends(get_db), _=Depends(current_user)):
    return _compile(db, body)


# ------------------------------------------------------------------ theory of computation
@router.get("/toc/fsm")
def fsm_describe(_=Depends(current_user)):
    return fsm.describe()


@router.get("/toc/fsm/{incident_id}")
def fsm_incident(incident_id: str, db: Session = Depends(get_db), _=Depends(current_user)):
    return pipeline.fsm_status(db, incidents.get_incident(db, incident_id))


class ReachIn(BaseModel):
    from_state: str


@router.post("/toc/reachability")
def reachability(body: ReachIn, _=Depends(current_user)):
    if body.from_state not in fsm.STATE_IDS:
        raise incidents.DomainError("UNKNOWN_STATE", f"Unknown state {body.from_state}", 422)
    return fsm.reachability(body.from_state)


class AcceptsIn(BaseModel):
    input: list[str]


@router.post("/toc/accepts")
def accepts(body: AcceptsIn, _=Depends(current_user)):
    return fsm.run([e.strip() for e in body.input if e.strip()])


class RegexIn(BaseModel):
    token_type: str
    text: str


@router.post("/toc/regex")
def regex(body: RegexIn, _=Depends(current_user)):
    try:
        return regex_accepts(body.token_type, body.text)
    except KeyError:
        raise incidents.DomainError("UNKNOWN_TOKEN_TYPE", f"Unknown token type {body.token_type}", 422) from None


class StateSpaceIn(BaseModel):
    requirement: dict[str, int]
    incident_id: str | None = None
    algorithm: Literal["bfs", "dfs", "ucs", "astar"] = "astar"
    max_states: int = Field(2000, ge=1, le=20000)


@router.post("/toc/state-space")
def state_space_ep(body: StateSpaceIn, db: Session = Depends(get_db), _=Depends(current_user)):
    if body.incident_id:
        inc = incidents.get_incident(db, body.incident_id)
        lat, lon = inc.lat, inc.lon
    else:
        lat, lon = 22.7196, 75.8577
    etas = resources.unit_etas(db, graph_service.get_graph(db), lat, lon)
    by_kind = {k: [e["eta_s"] for e in etas if e["kind"] == k] for k in resources.KINDS}
    from app.services import settings_store
    return state_space.search(body.requirement, by_kind, body.algorithm,
                              settings_store.get_constraints(db)["max_units_per_incident"], body.max_states)


@router.post("/hospitals/rank")
def rank_hospitals(body: dict, db: Session = Depends(get_db), _=Depends(current_user)):
    if body.get("incident_id"):
        inc = incidents.get_incident(db, body["incident_id"])
        lat, lon, itype = inc.lat, inc.lon, inc.type
        patients = body.get("patients") or hospitals.estimate_patients(inc.type, inc.severity, inc.people_affected)
    else:
        if body.get("lat") is None or body.get("lon") is None:
            raise incidents.DomainError("BAD_REQUEST", "Provide incident_id or lat/lon", 422)
        lat, lon, itype, patients = body["lat"], body["lon"], body.get("incident_type", "OTHER"), body.get("patients", 1)
    return hospitals.rank(db, lat, lon, int(patients), itype)
