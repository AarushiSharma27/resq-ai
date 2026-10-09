"""Multi-criteria decision engine: builds candidate response strategies and scores them
with operator-tunable weights (normalized weighted sum, every component in [0, 1])."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import models as m
from app.services import graph_service, hospitals, resources, settings_store
from app.services.bus import bus

SEV_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
TRAFFIC_FACTOR = {"LOW": 1.0, "MODERATE": 1.4, "HEAVY": 1.9, "SEVERE": 2.6}


def _requirement_variants(req: dict, severity: str, avail: dict) -> list[tuple[str, str, dict]]:
    base = {k: int(req.get(k, 0)) for k in resources.KINDS}
    reinforced = dict(base)
    reinforced["AMBULANCE"] += 1
    primary = max(("FIRE_TRUCK", "POLICE", "RESCUE"), key=lambda k: base[k])
    if base[primary]:
        reinforced[primary] += 1
    lean = {k: (max(1, v - 1) if v > 1 else v) for k, v in base.items()}
    out = [("A", "Requirement as stated, nearest units", base),
           ("B", "Reinforced response (+1 ambulance, +1 primary unit)", reinforced)]
    if SEV_RANK.get(severity, 1) <= 1 and lean != base:
        out.append(("C", "Lean response (keeps more reserve units free)", lean))
    else:
        out.append(("C", "Requirement as stated, alternate hospital", base))
    return out


def generate(db: Session, inc: m.Incident, weights: dict | None = None, commit: bool = True) -> dict:
    w = settings_store.normalize(weights) if weights else settings_store.get_weights(db)
    constraints = settings_store.get_constraints(db)
    g = graph_service.get_graph(db)
    req = inc.requirement or {}
    avail = resources.available_counts(db)
    patients = hospitals.estimate_patients(inc.type, inc.severity, inc.people_affected)
    ranking = hospitals.rank(db, inc.lat, inc.lon, patients, inc.type)
    feasible_h = [h for h in ranking if h["feasible"]]
    etas = resources.unit_etas(db, g, inc.lat, inc.lon)
    traffic_level = traffic_overall(g)

    strategies = []
    for sid, label, r in _requirement_variants(req, inc.severity, avail):
        violations: list[str] = []
        units = []
        for k in resources.KINDS:
            pool = [e for e in etas if e["kind"] == k]
            if r[k] > len(pool):
                violations.append(f"Needs {r[k]} {resources.LABEL[k]}, only {len(pool)} available")
            units += [{"code": e["code"], "kind": k, "eta_s": e["eta_s"], "resource_id": e["resource_id"],
                       "source_node": e["source_node"]} for e in pool[: r[k]]]
        if sum(r.values()) > constraints["max_units_per_incident"]:
            violations.append(f"Exceeds max {constraints['max_units_per_incident']} units per incident")
        if inc.severity == "CRITICAL" and r["AMBULANCE"] < constraints["min_ambulances_critical"]:
            violations.append(f"Critical incidents need >= {constraints['min_ambulances_critical']} ambulances")
        h = (feasible_h[1] if sid == "C" and len(feasible_h) > 1 and "alternate" in label else
             feasible_h[0] if feasible_h else None)
        if h is None:
            violations.append("No feasible hospital")
        response_time = max((u["eta_s"] for u in units), default=0.0)
        if response_time > constraints["max_response_time_s"]:
            violations.append(f"Response time {response_time:.0f}s exceeds limit {constraints['max_response_time_s']}s")
        first = min(units, key=lambda u: u["eta_s"]) if units else None
        route = g.route_points((g.nodes[first["source_node"]].lat, g.nodes[first["source_node"]].lon), (inc.lat, inc.lon),
                               "astar") if first else None
        total_units = max(1, sum(r.values()))
        coverage = min(1.0, sum(min(r[k], int(req.get(k, 0))) for k in resources.KINDS) / max(1, sum(int(v) for v in req.values())))
        reserve_left = sum(avail[k] - r[k] for k in resources.KINDS) / max(1, sum(avail.values()))
        sev_need = SEV_RANK.get(inc.severity, 1) + 1
        sev_match = min(1.0, (total_units / max(1, sum(int(v) for v in req.values()))) * (0.7 + 0.1 * sev_need))
        risk = round(max(0.0, 1 - coverage) * 0.6 + (0.4 if violations else 0.0), 3)
        metrics = {"response_time_s": round(response_time, 1), "distance_m": route["distance_m"] if route else None,
                   "hospital_available_beds": h["hospital"]["emergency_beds_available"] if h else 0,
                   "hospital_occupancy_pct": h["hospital"]["occupancy_pct"] if h else 100.0,
                   "traffic_factor": TRAFFIC_FACTOR[traffic_level], "risk": risk, "coverage": round(coverage, 3)}
        comp = {
            "response_time": max(0.0, 1 - response_time / 1800),
            "distance": max(0.0, 1 - (metrics["distance_m"] or 15000) / 15000),
            "resource_availability": max(0.0, reserve_left),
            "hospital_capacity": (h["score"] if h else 0.0),
            "severity_match": sev_match,
            "traffic": 1 / TRAFFIC_FACTOR[traffic_level],
            "risk": 1 - risk,
            "constraints": 0.0 if violations else 1.0,
        }
        score = round(sum(w[k] * comp[k] for k in w), 4)
        strategies.append({
            "id": sid, "label": f"Strategy {sid}", "description": label, "resources": r,
            "units": [{"code": u["code"], "kind": u["kind"], "eta_s": u["eta_s"]} for u in units],
            "hospital": {"id": h["hospital"]["id"], "name": h["hospital"]["name"]} if h else None,
            "route": {"label": f"Route {ord(sid) - 64}", "travel_time_s": route["travel_time_s"] if route else None,
                      "distance_m": route["distance_m"] if route else None, "path": route["path"] if route else [],
                      "geometry": route["geometry"] if route else []},
            "metrics": metrics, "score_breakdown": {k: round(v, 3) for k, v in comp.items()}, "score": score,
            "feasible": not violations, "violations": violations,
        })

    feasible = [s for s in strategies if s["feasible"]]
    best = max(feasible or strategies, key=lambda s: s["score"])
    others = [s for s in strategies if s is not best]
    reasons = []
    if all(best["metrics"]["response_time_s"] <= s["metrics"]["response_time_s"] for s in others):
        reasons.append("Lowest predicted response time")
    if best["feasible"]:
        reasons.append("Satisfies all operational constraints")
    if best["metrics"]["coverage"] >= 1:
        reasons.append("Fully covers the requested resources")
    if best["hospital"]:
        reasons.append(f"{best['hospital']['name']} has {best['metrics']['hospital_available_beds']} free emergency beds")
    reasons.append(f"Highest weighted score ({best['score']:.2f})")

    sev_pred = next((p for p in inc_predictions(db, inc.id) if p.model_name == "severity"), None)
    confidence = sev_pred.confidence if sev_pred and sev_pred.source == "ML" else None
    h0 = feasible_h[0] if feasible_h else None
    decision = {
        "incident_id": inc.id, "selected_id": best["id"], "strategies": strategies, "reasons": reasons,
        "explanation": {
            "resource": [f"{best['resources'][k]} {resources.LABEL[k]} (nearest ETA "
                         f"{min((u['eta_s'] for u in best['units'] if u['kind'] == k), default=0) / 60:.1f} min)"
                         for k in resources.KINDS if best["resources"][k]],
            "route": [f"A* on the time-weighted road graph, traffic level {traffic_level}",
                      f"{best['route']['label']}: {(best['route']['travel_time_s'] or 0) / 60:.1f} min, "
                      f"{(best['route']['distance_m'] or 0) / 1000:.2f} km"],
            "hospital": h0["reasons"] if h0 else ["No feasible hospital"],
            "priority": [f"Severity {inc.severity} ({inc.severity_source})", f"{inc.people_affected} people affected"],
        },
        "weights": w, "confidence": confidence,
        "confidence_note": "Severity model confidence" if confidence is not None
        else "Not available - severity model not trained (rule-based severity)",
        "hospital_ranking": ranking,
    }
    if commit:
        row = m.Decision(incident_id=inc.id, selected_label=best["id"], weights=w, data=decision, confidence=confidence)
        row.strategies = [m.ResponseStrategy(label=s["id"], data=s, score=s["score"], feasible=s["feasible"]) for s in strategies]
        db.add(row)
        db.commit()
        bus.publish("recommendation", {k: v for k, v in decision.items() if k != "hospital_ranking"}, inc.id)
    return decision


def inc_predictions(db: Session, incident_id: str) -> list[m.Prediction]:
    from sqlalchemy import select
    return list(db.scalars(select(m.Prediction).where(m.Prediction.incident_id == incident_id)
                           .order_by(m.Prediction.created_at.desc())))


def traffic_overall(g) -> str:
    roads = [e for e in g.edges.values() if not e.id.startswith("ACC_")]
    if not roads:
        return "LOW"
    avg = sum(e.traffic_factor for e in roads) / len(roads)
    return graph_service.level_for_factor(avg)
