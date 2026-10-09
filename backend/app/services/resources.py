"""Resource availability, ETA estimation and constraint-based allocation."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.optimization.graph import ACCESS_SPEED_KMH, RoadGraph
from app.services import graph_service
from app.services import serializers as ser
from app.services.bus import bus
from app.utils.geo import haversine_m

KINDS = ("AMBULANCE", "FIRE_TRUCK", "POLICE", "RESCUE")
LABEL = {"AMBULANCE": "ambulances", "FIRE_TRUCK": "fire trucks", "POLICE": "police units", "RESCUE": "rescue teams"}


def available_counts(db: Session) -> dict[str, int]:
    out = {k: 0 for k in KINDS}
    for r in db.scalars(select(m.Resource).where(m.Resource.status == "AVAILABLE")):
        out[r.kind] = out.get(r.kind, 0) + 1
    return out


def total_counts(db: Session) -> dict[str, int]:
    out = {k: 0 for k in KINDS}
    for r in db.scalars(select(m.Resource).where(m.Resource.status != "MAINTENANCE")):
        out[r.kind] = out.get(r.kind, 0) + 1
    return out


def position(r: m.Resource) -> tuple[float, float]:
    if r.location:
        return r.location.lat, r.location.lon
    return r.home_lat, r.home_lon


def unit_etas(db: Session, g: RoadGraph, lat: float, lon: float, kinds=KINDS) -> list[dict]:
    """ETA (s) of every AVAILABLE unit to the point, from one single-source Dijkstra."""
    target = g.nearest_node(lat, lon)
    tn = g.nodes[target]
    times = g.single_source(target, "time")
    dists = g.single_source(target, "distance")
    last_leg = haversine_m(tn.lat, tn.lon, lat, lon)
    out = []
    for r in db.scalars(select(m.Resource).where(m.Resource.status == "AVAILABLE", m.Resource.kind.in_(kinds))):
        plat, plon = position(r)
        src = g.nearest_node(plat, plon, kinds=("intersection", "station"))
        if src not in times:
            continue  # unreachable (roads blocked)
        sn = g.nodes[src]
        first_leg = haversine_m(plat, plon, sn.lat, sn.lon)
        eta = times[src] + (first_leg + last_leg) / (ACCESS_SPEED_KMH / 3.6)
        out.append({"resource_id": r.id, "code": r.code, "kind": r.kind, "station": r.station,
                    "eta_s": round(eta, 1), "distance_m": round(dists[src] + first_leg + last_leg, 1),
                    "source_node": src})
    out.sort(key=lambda x: x["eta_s"])
    return out


def allocate(db: Session, incident: m.Incident, requirement: dict, commit: bool = False) -> dict:
    """Greedy nearest-unit allocation per kind (optimal for independent kinds with a
    sum-of-ETA objective). Reports shortages with a suggested remedy."""
    g = graph_service.get_graph(db)
    etas = unit_etas(db, g, incident.lat, incident.lon)
    req = {k: max(0, int(requirement.get(k, 0) or 0)) for k in KINDS}
    avail = {k: sum(1 for e in etas if e["kind"] == k) for k in KINDS}
    assigned, shortages = [], []
    for k in KINDS:
        pool = [e for e in etas if e["kind"] == k]
        assigned.extend(pool[: req[k]])
        if req[k] > len(pool):
            shortages.append({"kind": k, "requested": req[k], "available": len(pool),
                              "suggestion": f"Search alternative resource allocation: request mutual aid for "
                                            f"{req[k] - len(pool)} {LABEL[k]} or substitute with rescue teams"})
    if commit and not shortages:
        by_id = {r.id: r for r in db.scalars(select(m.Resource).where(m.Resource.id.in_([a["resource_id"] for a in assigned])))}
        for a in assigned:
            r = by_id[a["resource_id"]]
            r.status, r.assigned_incident_id, r.eta_s = "DISPATCHED", incident.id, a["eta_s"]
            r.destination = incident.location_name or incident.title
        db.commit()
        bus.publish("resource_update", {"resources": [ser.resource(r) for r in by_id.values()]}, incident.id)
    return {"feasible": not shortages, "requested": req, "available": avail, "assigned": assigned,
            "shortages": shortages, "etas_by_kind": {k: [e["eta_s"] for e in etas if e["kind"] == k] for k in KINDS}}


def release(db: Session, incident_id: str) -> int:
    units = list(db.scalars(select(m.Resource).where(m.Resource.assigned_incident_id == incident_id)))
    for r in units:
        r.status, r.assigned_incident_id, r.eta_s, r.speed_kmh, r.destination = "AVAILABLE", None, None, 0.0, None
        if r.location:
            r.location.lat, r.location.lon = r.home_lat, r.home_lon
    db.commit()
    if units:
        bus.publish("resource_update", {"resources": [ser.resource(r) for r in units]}, incident_id)
    return len(units)
