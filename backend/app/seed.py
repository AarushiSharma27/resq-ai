"""Idempotent demo seed: users, road network, traffic, hospitals, fleet and agile board."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.security import hash_password
from app.services.city_data import (CAPACITY, CODE_PREFIX, EQUIPMENT, FLEET, HOSPITALS, INTERSECTIONS, ROADS,
                                    STATIONS)
from app.utils.geo import haversine_m

DEMO_USERS = [
    ("admin", "admin123", "ADMIN", "System Administrator"),
    ("operator", "operator123", "OPERATOR", "Dispatch Operator"),
    ("analyst", "analyst123", "ANALYST", "Data Analyst"),
    ("viewer", "viewer123", "VIEWER", "Read-only Viewer"),
]


def _empty(db: Session, model) -> bool:
    return (db.scalar(select(func.count()).select_from(model)) or 0) == 0


def seed(db: Session) -> None:
    if _empty(db, m.User):
        for u, p, r, n in DEMO_USERS:
            db.add(m.User(username=u, password_hash=hash_password(p), role=r, full_name=n))

    if _empty(db, m.Road):
        pos = {nid: (lat, lon) for nid, _, lat, lon in INTERSECTIONS}
        for rid, s, t, name, speed in ROADS:
            a, b = pos[s], pos[t]
            db.add(m.Road(id=rid, source=s, target=t, name=name, speed_kmh=speed,
                          distance_m=round(haversine_m(*a, *b) * 1.25, 1),  # straight line -> road-length factor
                          geometry=[list(a), list(b)]))
            db.add(m.Traffic(road_id=rid, traffic_level="LOW", traffic_factor=1.0))

    if _empty(db, m.Hospital):
        for code, name, lat, lon, specs, (er_t, er_o, icu_t, icu_o) in HOSPITALS:
            h = m.Hospital(code=code, name=name, lat=lat, lon=lon, node_id=f"H_{code}", specializations=specs)
            h.capacity = m.HospitalCapacity(emergency_beds_total=er_t, emergency_beds_occupied=er_o,
                                            icu_total=icu_t, icu_occupied=icu_o)
            db.add(h)

    if _empty(db, m.Resource):
        counters = {k: 100 for k in CODE_PREFIX}
        for sid, name, lat, lon, kind in STATIONS:
            for i in range(FLEET.get(sid, 0)):
                counters[kind] += 1
                # small offsets so markers at one station do not overlap exactly
                olat, olon = lat + (i % 3) * 0.0004, lon + (i // 3) * 0.0004
                r = m.Resource(code=f"{CODE_PREFIX[kind]}-{counters[kind]}", kind=kind, station=name,
                               home_lat=olat, home_lon=olon, capacity=CAPACITY[kind], equipment=EQUIPMENT[kind])
                r.location = m.ResourceLocation(lat=olat, lon=olon)
                db.add(r)

    if _empty(db, m.AgileSprint):
        now = datetime.now(timezone.utc)
        sprints = [
            ("Sprint 1", "Core platform: auth, DB schema, road graph", -42, "CLOSED"),
            ("Sprint 2", "Compiler pipeline and incident FSM", -28, "CLOSED"),
            ("Sprint 3", "Routing, allocation, hospital ranking", -14, "CLOSED"),
            ("Sprint 4", "ML models, decision engine, simulation, dashboard", 0, "ACTIVE"),
        ]
        objs = []
        for name, goal, offset, status in sprints:
            sp = m.AgileSprint(name=name, goal=goal, start=now + timedelta(days=offset),
                               end=now + timedelta(days=offset + 14), status=status)
            db.add(sp)
            objs.append(sp)
        db.flush()
        tasks = [
            (0, "JWT authentication & roles", "backend", 5, "DONE"), (0, "Database schema", "database", 8, "DONE"),
            (0, "City road graph seed", "optimization", 5, "DONE"),
            (1, "Lexer with regex token specs", "compiler", 5, "DONE"), (1, "Recursive-descent parser", "compiler", 8, "DONE"),
            (1, "Semantic analyzer & IR", "compiler", 8, "DONE"), (1, "Incident DFA", "toc", 5, "DONE"),
            (2, "Dijkstra / A* / BFS routing", "optimization", 8, "DONE"), (2, "Greedy resource allocation", "backend", 5, "DONE"),
            (2, "Hospital ranking", "backend", 5, "DONE"), (2, "State-space search", "toc", 8, "DONE"),
            (3, "ML training pipeline", "ml", 8, "DONE"), (3, "Decision engine", "backend", 8, "TESTING"),
            (3, "Simulation engine & WebSockets", "simulation", 8, "IN_PROGRESS"), (3, "Command Center UI", "frontend", 8, "IN_PROGRESS"),
            (3, "Analytics dashboard", "frontend", 5, "TODO"), (3, "IoT sensor simulator", "backend", 3, "TODO"),
            (None, "Live traffic API integration", "backend", 8, "BACKLOG"), (None, "Mobile responder app", "frontend", 13, "BACKLOG"),
        ]
        for sp_idx, title, module, pts, status in tasks:
            db.add(m.AgileTask(title=title, module=module, story_points=pts, status=status,
                               sprint_id=objs[sp_idx].id if sp_idx is not None else None,
                               assignee=["Team A", "Team B", "Team C"][len(title) % 3],
                               completed_at=objs[sp_idx].start + timedelta(days=3 + len(title) % 10)
                               if status == "DONE" and sp_idx is not None else None))
    db.commit()
