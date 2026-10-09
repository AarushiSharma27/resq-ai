"""ML, simulation, demo scenarios, events, analytics, IoT, agile, admin and academic mapping."""
from __future__ import annotations

import io
from collections import Counter
from datetime import datetime, timezone
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.database import get_db
from app.ml import service as ml
from app.security import ROLES, current_user, hash_password, require
from app.services import graph_service, incidents, pipeline, resources, settings_store
from app.services import serializers as ser
from app.services.city_data import GAZETTEER
from app.services.iot import iot
from app.simulation.engine import manager
from app.utils.geo import haversine_m

router = APIRouter(prefix="/api")
admin = require()
operator = require("OPERATOR")
analyst = require("ANALYST")


# ------------------------------------------------------------------ ML
@router.get("/ml/models")
def ml_models(db: Session = Depends(get_db), _=Depends(current_user)):
    return [ml.model_info(db, n) for n in ml.SPECS]


@router.get("/ml/models/{name}")
def ml_model(name: str, db: Session = Depends(get_db), _=Depends(current_user)):
    return ml.model_info(db, name)


@router.get("/ml/datasets")
def ml_datasets(db: Session = Depends(get_db), _=Depends(current_user)):
    return [ml.dataset_dict(d) for d in db.scalars(select(m.MLDataset).order_by(m.MLDataset.id.desc()))]


@router.get("/ml/schema/{name}")
def ml_schema(name: str, _=Depends(current_user)):
    return ml.schema(name)


@router.post("/ml/datasets/upload")
async def ml_upload(file: UploadFile = File(...), model_name: str = Form(...), db: Session = Depends(get_db),
                    _=Depends(analyst)):
    ml.schema(model_name)
    try:
        df = pd.read_csv(io.BytesIO(await file.read()))
    except Exception as e:
        raise ml.MLError("BAD_CSV", f"Could not parse CSV: {e}", 422) from None
    return ml.dataset_dict(ml.save_dataset(db, model_name, df, "UPLOADED", file.filename or "upload.csv"))


class GenerateIn(BaseModel):
    model_name: str
    rows: int = Field(1500, ge=50, le=50000)
    seed: int = 42


@router.post("/ml/datasets/generate")
def ml_generate(body: GenerateIn, db: Session = Depends(get_db), _=Depends(analyst)):
    df = ml.generate_frame(body.model_name, body.rows, body.seed)
    label = f"Synthetic {body.model_name} ({body.rows} rows, seed {body.seed})"
    return ml.dataset_dict(ml.save_dataset(db, body.model_name, df, "SYNTHETIC", label))


class TrainIn(BaseModel):
    model_name: str
    dataset_id: int
    algorithm: Literal["random_forest", "logistic_regression", "gradient_boosting", "linear_regression"] | None = None


@router.post("/ml/train")
def ml_train(body: TrainIn, db: Session = Depends(get_db), _=Depends(analyst)):
    ml.train(db, body.model_name, body.dataset_id, body.algorithm)
    return ml.model_info(db, body.model_name)


class NameIn(BaseModel):
    model_name: str


@router.post("/ml/evaluate")
def ml_evaluate(body: NameIn, db: Session = Depends(get_db), _=Depends(analyst)):
    return ml.model_info(db, body.model_name)


class PredictIn(BaseModel):
    model_name: str
    features: dict


@router.post("/ml/predict")
def ml_predict(body: PredictIn, db: Session = Depends(get_db), _=Depends(analyst)):
    return ml.predict(db, body.model_name, body.features)


# ------------------------------------------------------------------ simulation / demo
class Scenario(BaseModel):
    type: str
    location_name: str
    lat: float | None = None
    lon: float | None = None
    severity: str | None = None
    people_affected: int = 0
    resources: dict[str, int] | None = None
    traffic: Literal["LOW", "MODERATE", "HEAVY", "SEVERE"] | None = None
    hospital_load: Literal["NORMAL", "STRAINED"] | None = None


class SimIn(BaseModel):
    incident_id: str | None = None
    scenario: Scenario | None = None
    speed: Literal[1, 2, 5, 10] = 5


@router.post("/simulation/run")
def sim_run(body: SimIn, db: Session = Depends(get_db), _=Depends(operator)):
    if body.incident_id:
        inc = incidents.get_incident(db, body.incident_id)
        if inc.status != "ACTIVE":
            raise incidents.DomainError("NOT_ACTIVE", "Incident is not active", 409)
        if not db.scalars(select(m.Resource).where(m.Resource.assigned_incident_id == inc.id)).first():
            raise incidents.DomainError("NO_UNITS", "No units are assigned to this incident - run the pipeline first", 409)
    elif body.scenario:
        sc = body.scenario
        if sc.traffic:
            _set_traffic(db, sc.traffic)
        if sc.hospital_load == "STRAINED":
            for h in db.scalars(select(m.Hospital)):
                h.capacity.emergency_beds_occupied = int(h.capacity.emergency_beds_total * 0.9)
            db.commit()
        req = {k: v for k, v in (sc.resources or {}).items() if k in resources.KINDS}
        inc = incidents.create_incident(db, {"type": sc.type, "location_name": sc.location_name, "lat": sc.lat,
                                             "lon": sc.lon, "people_affected": sc.people_affected,
                                             "severity_estimate": sc.severity, "requirement": req})
        pipeline.respond(db, inc, pipeline.Stages())
    else:
        raise incidents.DomainError("BAD_REQUEST", "Provide incident_id or scenario", 422)
    run_id = manager.start(db, inc.id, body.speed)
    return {"run_id": run_id, "incident_id": inc.id, "status": "RUNNING"}


def _set_traffic(db: Session, level: str):
    from app.api.ops import LEVEL_FACTOR
    for t in db.scalars(select(m.Traffic)):
        t.traffic_level, t.traffic_factor = level, LEVEL_FACTOR[level]
    db.commit()
    graph_service.invalidate()


@router.get("/simulation/runs")
def sim_runs(db: Session = Depends(get_db), _=Depends(current_user)):
    from app.api.core import _run_summary
    return [_run_summary(r) for r in db.scalars(select(m.SimulationRun).order_by(m.SimulationRun.started_at.desc()).limit(100))]


@router.get("/simulation/{run_id}")
def sim_get(run_id: str, db: Session = Depends(get_db), _=Depends(current_user)):
    snap = manager.snapshot(db, run_id)
    if snap is None:
        raise incidents.DomainError("NOT_FOUND", f"Simulation {run_id} not found", 404)
    return snap


class SpeedIn(BaseModel):
    speed: Literal[1, 2, 5, 10]


@router.post("/simulation/{run_id}/speed")
def sim_speed(run_id: str, body: SpeedIn, db: Session = Depends(get_db), _=Depends(operator)):
    manager.set_speed(run_id, body.speed)
    row = db.get(m.SimulationRun, run_id)
    if row:
        row.speed = body.speed
        db.commit()
    return {"run_id": run_id, "speed": body.speed}


SCENARIOS = [
    ("school_fire", "School fire", "Fire with blocked exits at a school in Vijay Nagar.",
     "Fire at School A in Vijay Nagar, 500 students affected, 2 exits blocked, send 3 ambulances and 2 fire trucks, evacuate building",
     "FIRE", "SCHOOL_A"),
    ("highway_accident", "Multi-vehicle accident", "Pile-up on the Ring Road with injured passengers.",
     "Accident on Ring Road near Bengali Square, 12 people injured, heavy traffic, send 4 ambulances and 2 police units",
     "ACCIDENT", "BENGALI_SQUARE"),
    ("chemical_leak", "Chemical leak", "Toxic gas leak at an industrial unit.",
     "Chemical hazard at chemical plant in Pardeshipura, 200 people affected, toxic gas, send 2 fire trucks, 3 ambulances and 1 rescue team, evacuate area",
     "CHEMICAL_HAZARD", "CHEMICAL_PLANT"),
    ("market_medical", "Mass medical emergency", "Crowd collapse at a heritage market.",
     "Medical emergency at Sarafa Bazaar, 40 people affected, 8 injured, send 3 ambulances and 1 police unit",
     "MEDICAL", "SARAFA_BAZAAR"),
    ("flood_rescue", "Urban flooding", "Flooded residential area with trapped residents.",
     "Flood at Bhawarkuan, 300 people affected, 20 people trapped, send 2 rescue teams, 2 ambulances and 2 police units, evacuate area",
     "FLOOD", "BHAWARKUAN"),
]


@router.get("/demo/scenarios")
def demo_scenarios(_=Depends(current_user)):
    return [{"id": i, "title": t, "description": d, "command": c, "type": ty, "location_name": GAZETTEER[k][0],
             "lat": GAZETTEER[k][1], "lon": GAZETTEER[k][2]} for i, t, d, c, ty, k in SCENARIOS]


class LaunchIn(BaseModel):
    speed: Literal[1, 2, 5, 10] = 5


@router.post("/demo/scenarios/{scenario_id}/launch")
def demo_launch(scenario_id: str, body: LaunchIn | None = None, db: Session = Depends(get_db), _=Depends(operator)):
    sc = next((s for s in SCENARIOS if s[0] == scenario_id), None)
    if sc is None:
        raise incidents.DomainError("NOT_FOUND", f"Unknown scenario {scenario_id}", 404)
    return pipeline.run(db, sc[3], auto_simulate=True, speed=(body.speed if body else 5))


# ------------------------------------------------------------------ events / analytics
@router.get("/events")
def events(incident_id: str | None = None, event_type: str | None = None, limit: int = 200,
           db: Session = Depends(get_db), _=Depends(current_user)):
    stmt = select(m.IncidentEvent).order_by(m.IncidentEvent.id.desc()).limit(min(limit, 1000))
    if incident_id:
        stmt = stmt.where(m.IncidentEvent.incident_id == incident_id)
    if event_type:
        stmt = stmt.where(m.IncidentEvent.event_type == event_type)
    return [ser.event(e) for e in db.scalars(stmt)]


@router.get("/analytics")
def analytics(date_from: datetime | None = None, date_to: datetime | None = None, type: str | None = None,
              severity: str | None = None, location: str | None = None, db: Session = Depends(get_db),
              _=Depends(current_user)):
    stmt = select(m.Incident)
    if date_from:
        stmt = stmt.where(m.Incident.created_at >= date_from)
    if date_to:
        stmt = stmt.where(m.Incident.created_at <= date_to)
    if type:
        stmt = stmt.where(m.Incident.type == type)
    if severity:
        stmt = stmt.where(m.Incident.severity == severity)
    if location:
        stmt = stmt.where(m.Incident.location_name.ilike(f"%{location}%"))
    incs = list(db.scalars(stmt))
    ids = {i.id for i in incs}
    rts = [{"incident_id": i.id, "response_time_s": i.response_time_s, "type": i.type} for i in incs if i.response_time_s]
    all_res = list(db.scalars(select(m.Resource)))
    util = []
    for k in resources.KINDS:
        tot = [r for r in all_res if r.kind == k]
        busy = [r for r in tot if r.status not in ("AVAILABLE", "MAINTENANCE")]
        util.append({"kind": k, "total": len(tot), "busy": len(busy), "pct": round(100 * len(busy) / max(1, len(tot)), 1)})
    eff = []
    for r in db.scalars(select(m.Route).where(m.Route.purpose == "DISPATCH")):
        if r.incident_id in ids and len(r.geometry) >= 2:
            sl = haversine_m(*r.geometry[0], *r.geometry[-1])
            eff.append({"incident_id": r.incident_id, "optimal_s": r.travel_time_s, "straight_line_m": round(sl, 1),
                        "route_m": r.distance_m, "ratio": round(r.distance_m / sl, 3) if sl else None})
    spots = Counter((round(i.lat, 3), round(i.lon, 3), i.location_name) for i in incs)
    trans = Counter(f"{t.from_state} -> {t.to_state}" for t in db.scalars(select(m.StateTransition))
                    if t.incident_id in ids and t.from_state)
    mlp = []
    for name in ml.SPECS:
        info = ml.model_info(db, name)
        metric = "accuracy" if info["task"] == "classification" else "r2"
        mlp.append({"model": name, "status": info["status"], "metric": metric,
                    "value": (info["metrics"] or {}).get(metric)})
    sims = [{"run_id": r.id, "total_time_s": (r.metrics or {}).get("total_time_s"),
             "response_time_s": (r.metrics or {}).get("response_time_s")}
            for r in db.scalars(select(m.SimulationRun).where(m.SimulationRun.status == "COMPLETED"))]
    return {"by_type": [{"name": k, "count": v} for k, v in Counter(i.type for i in incs).most_common()],
            "by_severity": [{"name": s, "count": sum(1 for i in incs if i.severity == s)} for s in ml.SEVERITIES],
            "response_times": rts,
            "avg_response_time_s": round(sum(r["response_time_s"] for r in rts) / len(rts), 1) if rts else None,
            "resource_utilization": util,
            "hospital_utilization": [{"name": h.name, "occupancy_pct": ser.hospital(h)["occupancy_pct"]}
                                     for h in db.scalars(select(m.Hospital))],
            "route_efficiency": eff,
            "hotspots": [{"lat": a, "lon": b, "location": c, "count": n} for (a, b, c), n in spots.most_common(20)],
            "state_transition_freq": [{"transition": k, "count": v} for k, v in trans.most_common()],
            "ml_performance": mlp, "simulation_performance": sims}


# ------------------------------------------------------------------ IoT
@router.get("/iot/sensors")
def iot_sensors(_=Depends(current_user)):
    return {"mode": "SIMULATION", "speed": iot.speed, "sensors": iot.sensors_payload()}


@router.get("/iot/series/{sensor_id}")
def iot_series(sensor_id: str, limit: int = 60, _=Depends(current_user)):
    if sensor_id not in iot.series:
        raise incidents.DomainError("NOT_FOUND", f"Unknown sensor {sensor_id}", 404)
    return list(iot.series[sensor_id])[-limit:]


@router.post("/iot/speed")
def iot_speed(body: SpeedIn, _=Depends(operator)):
    iot.speed = body.speed
    return {"speed": iot.speed}


# ------------------------------------------------------------------ agile
def _sprint(s: m.AgileSprint) -> dict:
    return {"id": s.id, "name": s.name, "goal": s.goal, "start": ser.iso(s.start), "end": ser.iso(s.end), "status": s.status}


def _task(t: m.AgileTask) -> dict:
    return {"id": t.id, "title": t.title, "description": t.description, "status": t.status,
            "story_points": t.story_points, "sprint_id": t.sprint_id, "assignee": t.assignee, "module": t.module}


@router.get("/agile/sprints")
def sprints(db: Session = Depends(get_db), _=Depends(current_user)):
    return [_sprint(s) for s in db.scalars(select(m.AgileSprint).order_by(m.AgileSprint.start))]


@router.get("/agile/tasks")
def tasks(sprint_id: int | None = None, db: Session = Depends(get_db), _=Depends(current_user)):
    stmt = select(m.AgileTask).order_by(m.AgileTask.id)
    if sprint_id is not None:
        stmt = stmt.where(m.AgileTask.sprint_id == sprint_id)
    return [_task(t) for t in db.scalars(stmt)]


TaskStatus = Literal["BACKLOG", "TODO", "IN_PROGRESS", "TESTING", "DONE"]


class TaskIn(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    status: TaskStatus = "BACKLOG"
    story_points: int = Field(3, ge=0, le=100)
    sprint_id: int | None = None
    assignee: str = ""
    module: str = ""


class TaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    story_points: int | None = None
    sprint_id: int | None = None
    assignee: str | None = None
    module: str | None = None


@router.post("/agile/tasks")
def create_task(body: TaskIn, db: Session = Depends(get_db), _=Depends(operator)):
    t = m.AgileTask(**body.model_dump())
    db.add(t)
    db.commit()
    return _task(t)


@router.patch("/agile/tasks/{tid}")
def patch_task(tid: int, body: TaskPatch, db: Session = Depends(get_db), _=Depends(operator)):
    t = db.get(m.AgileTask, tid)
    if t is None:
        raise incidents.DomainError("NOT_FOUND", f"Task {tid} not found", 404)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    if body.status == "DONE" and t.completed_at is None:
        t.completed_at = datetime.now(timezone.utc)
    elif body.status and body.status != "DONE":
        t.completed_at = None
    db.commit()
    return _task(t)


@router.delete("/agile/tasks/{tid}")
def delete_task(tid: int, db: Session = Depends(get_db), _=Depends(operator)):
    t = db.get(m.AgileTask, tid)
    if t:
        db.delete(t)
        db.commit()
    return {"ok": True}


@router.get("/agile/metrics")
def agile_metrics(sprint_id: int | None = None, db: Session = Depends(get_db), _=Depends(current_user)):
    sps = list(db.scalars(select(m.AgileSprint).order_by(m.AgileSprint.start)))
    all_tasks = list(db.scalars(select(m.AgileTask)))
    velocity = [{"sprint": s.name, "points": sum(t.story_points for t in all_tasks if t.sprint_id == s.id and t.status == "DONE")}
                for s in sps]
    sp = next((s for s in sps if s.id == sprint_id), None) or next((s for s in sps if s.status == "ACTIVE"), None)
    scoped = [t for t in all_tasks if sp is None or t.sprint_id == sp.id]
    total = sum(t.story_points for t in scoped)
    burndown = []
    if sp:
        days = max(1, (sp.end - sp.start).days)
        start = sp.start if sp.start.tzinfo else sp.start.replace(tzinfo=timezone.utc)
        for d in range(days + 1):
            cutoff = start.timestamp() + d * 86400
            done = sum(t.story_points for t in scoped if t.completed_at and
                       (t.completed_at if t.completed_at.tzinfo else t.completed_at.replace(tzinfo=timezone.utc)).timestamp() <= cutoff)
            burndown.append({"day": d, "remaining": total - done, "ideal": round(total * (1 - d / days), 1)})
    return {"velocity": velocity, "completed_tasks": sum(1 for t in scoped if t.status == "DONE"), "total_tasks": len(scoped),
            "story_points_done": sum(t.story_points for t in scoped if t.status == "DONE"), "story_points_total": total,
            "burndown": burndown, "sprint_id": sp.id if sp else None}


# ------------------------------------------------------------------ admin
@router.get("/admin/users")
def users(db: Session = Depends(get_db), _=Depends(admin)):
    return [ser.user(u) for u in db.scalars(select(m.User).order_by(m.User.id))]


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6)
    role: Literal["ADMIN", "OPERATOR", "ANALYST", "VIEWER"]
    full_name: str = ""


@router.post("/admin/users")
def create_user(body: UserIn, db: Session = Depends(get_db), _=Depends(admin)):
    if db.scalar(select(m.User).where(m.User.username == body.username)):
        raise incidents.DomainError("DUPLICATE", f"User {body.username} already exists", 409)
    assert body.role in ROLES
    u = m.User(username=body.username, password_hash=hash_password(body.password), role=body.role, full_name=body.full_name)
    db.add(u)
    db.commit()
    return ser.user(u)


@router.delete("/admin/users/{uid}")
def delete_user(uid: int, db: Session = Depends(get_db), me: m.User = Depends(admin)):
    if uid == me.id:
        raise incidents.DomainError("SELF_DELETE", "You cannot delete your own account", 409)
    u = db.get(m.User, uid)
    if u:
        db.delete(u)
        db.commit()
    return {"ok": True}


@router.get("/admin/constraints")
def get_constraints(db: Session = Depends(get_db), _=Depends(current_user)):
    return settings_store.get_constraints(db)


@router.put("/admin/constraints")
def put_constraints(body: dict, db: Session = Depends(get_db), _=Depends(admin)):
    return settings_store.put_constraints(db, body)


# ------------------------------------------------------------------ academic mapping
@router.get("/academic/mapping")
def academic(_=Depends(current_user)):
    return [
        {"subject": "Compiler Design", "items": [
            {"concept": "Lexical analysis (regular expressions)", "where": "Tokenizer", "module_path": "backend/app/compiler/lexer.py", "endpoint": "/api/compiler/lex", "page": "/compiler"},
            {"concept": "Context-free grammar & recursive-descent parsing", "where": "Parser", "module_path": "backend/app/compiler/parser.py", "endpoint": "/api/compiler/parse", "page": "/compiler"},
            {"concept": "Semantic analysis & symbol table", "where": "Analyzer", "module_path": "backend/app/compiler/semantic.py", "endpoint": "/api/compiler/validate", "page": "/compiler"},
            {"concept": "Intermediate representation & code generation", "where": "IR / execution plan", "module_path": "backend/app/compiler/ir.py", "endpoint": "/api/compiler/compile", "page": "/command"}]},
        {"subject": "Theory of Computation", "items": [
            {"concept": "Deterministic finite automaton", "where": "Incident lifecycle", "module_path": "backend/app/toc/fsm.py", "endpoint": "/api/toc/fsm", "page": "/toc"},
            {"concept": "Language acceptance", "where": "DFA tester", "module_path": "backend/app/toc/fsm.py", "endpoint": "/api/toc/accepts", "page": "/toc"},
            {"concept": "Reachability (BFS)", "where": "State graph analysis", "module_path": "backend/app/toc/fsm.py", "endpoint": "/api/toc/reachability", "page": "/toc"}]},
        {"subject": "Artificial Intelligence", "items": [
            {"concept": "State-space search (BFS/DFS/UCS/A*)", "where": "Alternative allocation", "module_path": "backend/app/toc/state_space.py", "endpoint": "/api/toc/state-space", "page": "/toc"},
            {"concept": "Multi-criteria decision making", "where": "Decision engine", "module_path": "backend/app/services/decision.py", "endpoint": "/api/decision/generate", "page": "/command"}]},
        {"subject": "Design & Analysis of Algorithms", "items": [
            {"concept": "Dijkstra, A*, BFS shortest paths", "where": "Routing", "module_path": "backend/app/optimization/graph.py", "endpoint": "/api/routes/compare", "page": "/routing"},
            {"concept": "Greedy allocation", "where": "Resource allocation", "module_path": "backend/app/services/resources.py", "endpoint": "/api/resources/allocate", "page": "/resources"}]},
        {"subject": "Machine Learning", "items": [
            {"concept": "Classification & regression with held-out evaluation", "where": "ML models", "module_path": "backend/app/ml/service.py", "endpoint": "/api/ml/train", "page": "/ml"}]},
        {"subject": "Software Engineering (Agile)", "items": [
            {"concept": "Sprints, kanban, burndown, velocity", "where": "Agile board", "module_path": "backend/app/api/platform.py", "endpoint": "/api/agile/metrics", "page": "/agile"}]},
    ]
