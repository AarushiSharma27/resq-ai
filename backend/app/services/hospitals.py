"""Hospital ranking: multi-criteria scoring over capacity, travel time and specialisation."""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.services import graph_service, settings_store
from app.services import serializers as ser

NEEDED_SPECIALIZATION = {
    "FIRE": ["burns", "trauma"], "ACCIDENT": ["trauma", "orthopedic"], "MEDICAL": ["cardiac", "general"],
    "CHEMICAL_HAZARD": ["toxicology", "general"], "EARTHQUAKE": ["trauma", "orthopedic"],
    "FLOOD": ["general"], "CRIME": ["trauma"], "MISSING_PERSON": ["general", "pediatric"], "OTHER": ["general"],
}
# Transparent heuristic (not a learned model): expected share of affected people needing hospital care.
CASUALTY_RATE = {"LOW": 0.01, "MEDIUM": 0.03, "HIGH": 0.06, "CRITICAL": 0.10}


def estimate_patients(incident_type: str, severity: str, affected: int, injured: int = 0) -> int:
    if injured:
        return injured
    base = math.ceil(affected * CASUALTY_RATE.get(severity, 0.03))
    if incident_type in ("MEDICAL", "ACCIDENT"):
        base = max(base, 1)
    return base


def rank(db: Session, lat: float, lon: float, patients: int, incident_type: str = "OTHER") -> list[dict]:
    g = graph_service.get_graph(db)
    src = g.nearest_node(lat, lon)
    times = g.single_source(src, "time")
    constraints = settings_store.get_constraints(db)
    need = NEEDED_SPECIALIZATION.get(incident_type, ["general"])
    out = []
    for h in db.scalars(select(m.Hospital)):
        hd = ser.hospital(h)
        node = f"H_{h.code}"
        t = times.get(node)
        reasons, feasible = [], True
        if t is None:
            feasible = False
            reasons.append("Unreachable: all access roads blocked")
            t = float("inf")
        spec_match = [s for s in need if s in hd["specializations"]]
        cap_ok = hd["emergency_beds_available"] >= max(1, patients)
        if hd["emergency_beds_available"] == 0:
            feasible = False
            reasons.append("No emergency beds available")
        if hd["occupancy_pct"] >= constraints["max_hospital_occupancy_pct"]:
            feasible = False
            reasons.append(f"Occupancy {hd['occupancy_pct']}% ≥ limit {constraints['max_hospital_occupancy_pct']}%")
        s_time = max(0.0, 1 - (t / 1800)) if math.isfinite(t) else 0.0
        s_cap = min(1.0, hd["emergency_beds_available"] / max(1, patients))
        s_occ = 1 - hd["occupancy_pct"] / 100
        s_spec = 1.0 if spec_match else 0.4
        score = round(0.35 * s_time + 0.25 * s_cap + 0.20 * s_occ + 0.20 * s_spec, 4) if feasible else 0.0
        if feasible:
            reasons.append(f"{hd['occupancy_pct']:.0f}% current occupancy")
            reasons.append(f"{hd['emergency_beds_available']} available emergency beds"
                           + ("" if cap_ok else f" (fewer than ~{patients} expected patients)"))
            reasons.append(f"{t / 60:.1f} minute predicted travel time")
            reasons.append(f"Specialisation match: {', '.join(spec_match)}" if spec_match
                           else f"No {'/'.join(need)} specialisation")
            reasons.append("No current overload" if hd["load_status"] in ("LOW", "MODERATE") else f"Load status {hd['load_status']}")
        route = g.route_points((lat, lon), (h.lat, h.lon), "astar", dst_kinds=("hospital",)) if feasible else None
        out.append({"hospital": hd, "score": score, "travel_time_s": round(t, 1) if math.isfinite(t) else None,
                    "distance_m": route["distance_m"] if route else None, "feasible": feasible,
                    "capacity_sufficient": cap_ok, "specialization_match": spec_match, "reasons": reasons,
                    "route": route, "components": {"time": round(s_time, 3), "capacity": round(s_cap, 3),
                                                   "occupancy": round(s_occ, 3), "specialization": s_spec}})
    out.sort(key=lambda x: (-x["score"], x["travel_time_s"] or 1e9))
    return out
