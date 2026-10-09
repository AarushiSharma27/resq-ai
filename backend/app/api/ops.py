"""Road graph, routing, traffic, resources, hospitals and decision endpoints."""
from __future__ import annotations

import random
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.database import get_db
from app.optimization.graph import node_payload
from app.security import current_user, require
from app.services import decision as decision_svc
from app.services import graph_service, incidents, resources, settings_store
from app.services import serializers as ser
from app.services.bus import bus
from app.services.events import log_event
from app.utils.geo import haversine_m

router = APIRouter(prefix="/api")
admin = require()
operator = require("OPERATOR")
LEVEL_FACTOR = {"LOW": 1.0, "MODERATE": 1.4, "HEAVY": 1.9, "SEVERE": 2.6}


# ------------------------------------------------------------------ graph / routes
@router.get("/graph")
def graph(db: Session = Depends(get_db), _=Depends(current_user)):
    g = graph_service.get_graph(db)
    nodes = [node_payload(n) for n in g.nodes.values()]
    for i in db.scalars(select(m.Incident).where(m.Incident.status == "ACTIVE")):
        nodes.append({"id": i.id, "name": i.title, "kind": "incident", "lat": i.lat, "lon": i.lon})
    return {"nodes": nodes, "edges": [e.to_dict() for e in g.edges.values()]}


class EdgeIn(BaseModel):
    source: str
    target: str
    name: str
    speed_kmh: float = Field(gt=0, le=120)


@router.post("/graph/edges")
def add_edge(body: EdgeIn, db: Session = Depends(get_db), _=Depends(admin)):
    g = graph_service.get_graph(db)
    if body.source not in g.nodes or body.target not in g.nodes:
        raise incidents.DomainError("UNKNOWN_NODE", "Source and target must be existing graph nodes", 422)
    a, b = g.nodes[body.source], g.nodes[body.target]
    rid = f"R{len(db.scalars(select(m.Road.id)).all()) + 1:02d}X"
    db.add(m.Road(id=rid, source=a.id, target=b.id, name=body.name, speed_kmh=body.speed_kmh,
                  distance_m=round(haversine_m(a.lat, a.lon, b.lat, b.lon) * 1.25, 1),
                  geometry=[[a.lat, a.lon], [b.lat, b.lon]]))
    db.add(m.Traffic(road_id=rid))
    db.commit()
    graph_service.invalidate()
    return graph_service.get_graph(db).edges[rid].to_dict()


class Point(BaseModel):
    node_id: str | None = None
    lat: float | None = None
    lon: float | None = None


class RouteIn(BaseModel):
    source: Point
    target: Point
    algorithm: Literal["dijkstra", "astar", "bfs"] = "astar"
    weight: Literal["time", "distance"] = "time"


def _route(db: Session, src: Point, dst: Point, algorithm: str, weight: str) -> dict:
    g = graph_service.get_graph(db)
    if src.node_id and dst.node_id:
        for nid in (src.node_id, dst.node_id):
            if nid not in g.nodes:
                raise incidents.DomainError("UNKNOWN_NODE", f"Unknown node {nid}", 422)
        r = g.shortest(src.node_id, dst.node_id, algorithm, weight)
        if r["found"] and r["travel_time_s"] is None:
            r["travel_time_s"] = round(sum(g.edges[e].travel_time_s for e in r["edges"]), 1)
    else:
        def coords(p: Point):
            if p.node_id:
                n = g.nodes[p.node_id]
                return n.lat, n.lon
            if p.lat is None or p.lon is None:
                raise incidents.DomainError("BAD_POINT", "Point needs node_id or lat/lon", 422)
            return p.lat, p.lon
        r = g.route_points(coords(src), coords(dst), algorithm, weight)
    r["label"] = f"{algorithm.upper()} ({weight})"
    return r


@router.post("/routes/optimize")
def optimize(body: RouteIn, db: Session = Depends(get_db), _=Depends(current_user)):
    return _route(db, body.source, body.target, body.algorithm, body.weight)


class CompareIn(BaseModel):
    source: Point
    target: Point
    weight: Literal["time", "distance"] = "time"


@router.post("/routes/compare")
def compare(body: CompareIn, db: Session = Depends(get_db), _=Depends(current_user)):
    return {"results": [_route(db, body.source, body.target, a, body.weight) for a in ("dijkstra", "astar", "bfs")]}


# ------------------------------------------------------------------ traffic
def traffic_payload(db: Session) -> dict:
    g = graph_service.get_graph(db)
    roads = [e for e in g.edges.values() if not e.id.startswith("ACC_")]
    corridors = []
    for i in db.scalars(select(m.Incident).where(m.Incident.status == "ACTIVE")):
        r = db.scalar(select(m.Route).where(m.Route.incident_id == i.id).order_by(m.Route.id.desc()))
        if r:
            corridors.append({"incident_id": i.id, "edges": [e for e in _edges_on_path(g, r.path)]})
    return {"overall_level": decision_svc.traffic_overall(g), "mode": "SIMULATION",
            "edges": [{"edge_id": e.id, "name": e.name, "traffic_level": e.traffic_level, "traffic_factor": e.traffic_factor,
                       "speed_kmh": round(e.effective_speed_kmh, 1), "blocked": e.blocked,
                       "signal_priority": e.signal_priority, "accident": e.accident} for e in roads],
            "closures": [e.id for e in roads if e.blocked], "accidents": [e.id for e in roads if e.accident],
            "corridors": corridors,
            "avg_speed_kmh": round(sum(e.effective_speed_kmh for e in roads) / max(1, len(roads)), 1)}


def _edges_on_path(g, path: list[str]) -> list[str]:
    out = []
    for a, b in zip(path, path[1:]):
        for v, eid in g.adj.get(a, []):
            if v == b:
                out.append(eid)
                break
    return out


@router.get("/traffic")
def traffic(db: Session = Depends(get_db), _=Depends(current_user)):
    return traffic_payload(db)


class TrafficEventIn(BaseModel):
    edge_id: str
    event: Literal["ROAD_BLOCKED", "ACCIDENT", "HEAVY_TRAFFIC", "SIGNAL_PRIORITY", "CLEAR"]


@router.post("/traffic/event")
def traffic_event(body: TrafficEventIn, db: Session = Depends(get_db), _=Depends(operator)):
    t = db.scalar(select(m.Traffic).where(m.Traffic.road_id == body.edge_id))
    if t is None:
        raise incidents.DomainError("UNKNOWN_EDGE", f"Unknown road {body.edge_id}", 404)
    if body.event == "ROAD_BLOCKED":
        t.blocked = True
    elif body.event == "ACCIDENT":
        t.accident, t.traffic_level, t.traffic_factor = True, "SEVERE", LEVEL_FACTOR["SEVERE"]
    elif body.event == "HEAVY_TRAFFIC":
        t.traffic_level, t.traffic_factor = "HEAVY", LEVEL_FACTOR["HEAVY"]
    elif body.event == "SIGNAL_PRIORITY":
        t.signal_priority = True
    else:
        t.blocked = t.accident = t.signal_priority = False
        t.traffic_level, t.traffic_factor = "LOW", 1.0
    db.commit()
    graph_service.invalidate()
    g = graph_service.get_graph(db)
    log_event(db, "TRAFFIC_EVENT", f"{body.event} on {g.edges[body.edge_id].name}", payload={"edge_id": body.edge_id})

    # Re-route active incidents whose current route uses this road.
    rerouted = []
    for inc in db.scalars(select(m.Incident).where(m.Incident.status == "ACTIVE")):
        old = db.scalar(select(m.Route).where(m.Route.incident_id == inc.id).order_by(m.Route.id.desc()))
        if old is None or body.edge_id not in _edges_on_path(g, old.path):
            continue
        start = g.nodes[old.path[0]]
        new = g.route_points((start.lat, start.lon), (inc.lat, inc.lon), "astar")
        if not new["found"]:
            continue
        new["label"] = f"Re-route after {body.event.lower().replace('_', ' ')}"
        db.add(m.Route(incident_id=inc.id, purpose="DISPATCH", algorithm="astar", path=new["path"], geometry=new["geometry"],
                       distance_m=new["distance_m"], travel_time_s=new["travel_time_s"],
                       nodes_expanded=new["nodes_expanded"], label=new["label"]))
        db.commit()
        if inc.state in ("ROUTING", "ACTIVE_RESPONSE"):
            incidents.transition(db, inc, inc.state, f"{body.event} on {body.edge_id}", event="reroute")
        rerouted.append({"incident_id": inc.id, "old_travel_time_s": old.travel_time_s,
                         "new_travel_time_s": new["travel_time_s"], "route": new})
        bus.publish("route_change", {"route": new, "reason": f"{body.event} on {body.edge_id}"}, inc.id)
    bus.publish("traffic_update", {"edges": traffic_payload(db)["edges"]})
    return {"edge": g.edges[body.edge_id].to_dict(), "rerouted": rerouted}


# ------------------------------------------------------------------ resources
@router.get("/resources")
def list_resources(kind: str | None = None, status: str | None = None, db: Session = Depends(get_db),
                   _=Depends(current_user)):
    stmt = select(m.Resource).order_by(m.Resource.kind, m.Resource.code)
    if kind:
        stmt = stmt.where(m.Resource.kind == kind)
    if status:
        stmt = stmt.where(m.Resource.status == status)
    return [ser.resource(r) for r in db.scalars(stmt)]


class ResourceIn(BaseModel):
    code: str
    kind: Literal["AMBULANCE", "FIRE_TRUCK", "POLICE", "RESCUE"]
    station: str = ""
    lat: float
    lon: float
    capacity: int = 2
    equipment: list[str] = []


@router.post("/resources")
def create_resource(body: ResourceIn, db: Session = Depends(get_db), _=Depends(admin)):
    if db.scalar(select(m.Resource).where(m.Resource.code == body.code)):
        raise incidents.DomainError("DUPLICATE", f"Resource {body.code} already exists", 409)
    r = m.Resource(code=body.code, kind=body.kind, station=body.station, home_lat=body.lat, home_lon=body.lon,
                   capacity=body.capacity, equipment=body.equipment)
    r.location = m.ResourceLocation(lat=body.lat, lon=body.lon)
    db.add(r)
    db.commit()
    return ser.resource(r)


class ResourcePatch(BaseModel):
    status: Literal["AVAILABLE", "DISPATCHED", "EN_ROUTE", "ON_SCENE", "TRANSPORTING", "AT_HOSPITAL", "RETURNING",
                    "MAINTENANCE"] | None = None
    lat: float | None = None
    lon: float | None = None


def _resource(db: Session, rid: int) -> m.Resource:
    r = db.get(m.Resource, rid)
    if r is None:
        raise incidents.DomainError("NOT_FOUND", f"Resource {rid} not found", 404)
    return r


@router.patch("/resources/{rid}")
def patch_resource(rid: int, body: ResourcePatch, db: Session = Depends(get_db), _=Depends(operator)):
    r = _resource(db, rid)
    if body.status:
        r.status = body.status
    if body.lat is not None and body.lon is not None:
        r.location.lat, r.location.lon = body.lat, body.lon
    db.commit()
    bus.publish("resource_update", {"resources": [ser.resource(r)]})
    return ser.resource(r)


@router.delete("/resources/{rid}")
def delete_resource(rid: int, db: Session = Depends(get_db), _=Depends(admin)):
    db.delete(_resource(db, rid))
    db.commit()
    return {"ok": True}


class AllocateIn(BaseModel):
    incident_id: str
    requirement: dict[str, int]
    commit: bool = False


@router.post("/resources/allocate")
def allocate(body: AllocateIn, db: Session = Depends(get_db), _=Depends(operator)):
    return resources.allocate(db, incidents.get_incident(db, body.incident_id), body.requirement, body.commit)


# ------------------------------------------------------------------ hospitals
@router.get("/hospitals")
def list_hospitals(db: Session = Depends(get_db), _=Depends(current_user)):
    return [ser.hospital(h) for h in db.scalars(select(m.Hospital).order_by(m.Hospital.code))]


class HospitalIn(BaseModel):
    code: str
    name: str
    lat: float
    lon: float
    specializations: list[str] = []
    emergency_beds_total: int = Field(ge=0)
    emergency_beds_occupied: int = Field(0, ge=0)
    icu_total: int = Field(0, ge=0)
    icu_occupied: int = Field(0, ge=0)


@router.post("/hospitals")
def create_hospital(body: HospitalIn, db: Session = Depends(get_db), _=Depends(admin)):
    h = m.Hospital(code=body.code, name=body.name, lat=body.lat, lon=body.lon, node_id=f"H_{body.code}",
                   specializations=body.specializations)
    h.capacity = m.HospitalCapacity(emergency_beds_total=body.emergency_beds_total,
                                    emergency_beds_occupied=body.emergency_beds_occupied,
                                    icu_total=body.icu_total, icu_occupied=body.icu_occupied)
    db.add(h)
    db.commit()
    graph_service.invalidate()
    return ser.hospital(h)


class HospitalPatch(BaseModel):
    emergency_beds_occupied: int | None = Field(None, ge=0)
    icu_occupied: int | None = Field(None, ge=0)
    emergency_beds_total: int | None = Field(None, ge=0)
    icu_total: int | None = Field(None, ge=0)


@router.patch("/hospitals/{hid}")
def patch_hospital(hid: int, body: HospitalPatch, db: Session = Depends(get_db), _=Depends(operator)):
    h = db.get(m.Hospital, hid)
    if h is None:
        raise incidents.DomainError("NOT_FOUND", f"Hospital {hid} not found", 404)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(h.capacity, k, v)
    c = h.capacity
    c.emergency_beds_occupied = min(c.emergency_beds_occupied, c.emergency_beds_total)
    c.icu_occupied = min(c.icu_occupied, c.icu_total)
    db.commit()
    bus.publish("hospital_update", {"hospitals": [ser.hospital(h)]})
    return ser.hospital(h)


def simulate_hospitals(db: Session) -> list[dict]:
    for h in db.scalars(select(m.Hospital)):
        c = h.capacity
        c.emergency_beds_occupied = max(0, min(c.emergency_beds_total, c.emergency_beds_occupied + random.choice([-2, -1, 0, 1, 2])))
        c.icu_occupied = max(0, min(c.icu_total, c.icu_occupied + random.choice([-1, 0, 0, 1])))
    db.commit()
    out = [ser.hospital(h) for h in db.scalars(select(m.Hospital).order_by(m.Hospital.code))]
    bus.publish("hospital_update", {"hospitals": out})
    return out


@router.post("/hospitals/simulate-update")
def hospitals_simulate(db: Session = Depends(get_db), _=Depends(operator)):
    return simulate_hospitals(db)


# ------------------------------------------------------------------ decision
@router.get("/decision/weights")
def get_weights(db: Session = Depends(get_db), _=Depends(current_user)):
    return settings_store.get_weights(db)


@router.put("/decision/weights")
def put_weights(body: dict[str, float], db: Session = Depends(get_db), _=Depends(admin)):
    return settings_store.put_weights(db, body)


class DecisionIn(BaseModel):
    incident_id: str
    weights: dict[str, float] | None = None


@router.post("/decision/generate")
def generate(body: DecisionIn, db: Session = Depends(get_db), _=Depends(operator)):
    d = decision_svc.generate(db, incidents.get_incident(db, body.incident_id), body.weights)
    return {k: v for k, v in d.items() if k != "hospital_ranking"}
