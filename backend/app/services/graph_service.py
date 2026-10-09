"""Builds (and caches) the RoadGraph from the database."""
from __future__ import annotations

import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.optimization.graph import GEdge, GNode, RoadGraph
from app.services.city_data import INTERSECTIONS, STATIONS
from app.utils.geo import haversine_m

_lock = threading.Lock()
_graph: RoadGraph | None = None


def invalidate() -> None:
    global _graph
    with _lock:
        _graph = None


def level_for_factor(f: float) -> str:
    if f < 1.25:
        return "LOW"
    if f < 1.6:
        return "MODERATE"
    if f < 2.2:
        return "HEAVY"
    return "SEVERE"


def _access_edge(g: RoadGraph, node: GNode) -> None:
    inter = [n for n in g.nodes.values() if n.kind == "intersection"]
    near = min(inter, key=lambda n: haversine_m(node.lat, node.lon, n.lat, n.lon))
    d = haversine_m(node.lat, node.lon, near.lat, near.lon) * 1.2
    g.add_edge(GEdge(f"ACC_{node.id}", node.id, near.id, f"Access road ({node.name})", max(d, 50.0), 25.0,
                     [[node.lat, node.lon], [near.lat, near.lon]]))


def build(db: Session) -> RoadGraph:
    g = RoadGraph()
    for nid, name, lat, lon in INTERSECTIONS:
        g.add_node(GNode(nid, name, "intersection", lat, lon))
    traffic = {t.road_id: t for t in db.scalars(select(m.Traffic))}
    for r in db.scalars(select(m.Road)):
        if r.source not in g.nodes or r.target not in g.nodes:
            continue
        e = GEdge(r.id, r.source, r.target, r.name, r.distance_m, r.speed_kmh, r.geometry)
        t = traffic.get(r.id)
        if t:
            e.traffic_level, e.traffic_factor, e.blocked = t.traffic_level, t.traffic_factor, t.blocked
            e.accident, e.signal_priority = t.accident, t.signal_priority
        g.add_edge(e)
    for sid, name, lat, lon, _kind in STATIONS:
        n = GNode(sid, name, "station", lat, lon)
        g.add_node(n)
        _access_edge(g, n)
    for h in db.scalars(select(m.Hospital)):
        n = GNode(f"H_{h.code}", h.name, "hospital", h.lat, h.lon)
        g.add_node(n)
        _access_edge(g, n)
    return g


def get_graph(db: Session) -> RoadGraph:
    global _graph
    with _lock:
        if _graph is None:
            _graph = build(db)
        return _graph
