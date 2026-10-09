"""End-to-end response pipeline: NL command -> compiler -> ML -> FSM -> allocation ->
routing -> hospital -> decision -> (simulation) -> response plan."""
from __future__ import annotations

import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.compiler import SemanticContext, compile_command
from app.ml import service as ml
from app.services import decision as decision_svc
from app.services import graph_service, hospitals, incidents, resources, settings_store
from app.services import serializers as ser
from app.services.bus import bus
from app.services.events import log_event
from app.toc import fsm, state_space

STAGES = [
    ("lexical", "Lexical Analysis"), ("parsing", "Syntax Analysis"), ("semantic", "Semantic Analysis"),
    ("ir", "Intermediate Representation"), ("severity", "Severity Prediction"),
    ("resource_prediction", "Resource Demand"), ("fsm", "Incident State Machine"),
    ("allocation", "Resource Allocation"), ("routing", "Route Optimization"), ("hospital", "Hospital Allocation"),
    ("decision", "Decision Engine"), ("simulation", "Simulation"), ("plan", "Response Plan"),
]
KIND_KEYS = {"AMBULANCE": "ambulances", "FIRE_TRUCK": "fire_trucks", "POLICE": "police", "RESCUE": "rescue"}


class Stages:
    def __init__(self):
        self.items = {k: {"key": k, "title": t, "status": "skipped", "duration_ms": 0.0, "summary": "", "output": {}}
                      for k, t in STAGES}
        self._t = time.perf_counter()

    def start(self):
        self._t = time.perf_counter()

    def done(self, key: str, summary: str, output: dict | None = None, status: str = "ok", duration_ms: float | None = None):
        self.items[key].update(status=status, summary=summary, output=output or {},
                               duration_ms=round(duration_ms if duration_ms is not None else (time.perf_counter() - self._t) * 1000, 2))
        self.start()

    def list(self) -> list[dict]:
        return list(self.items.values())


def semantic_context(db: Session) -> SemanticContext:
    hosp = {h.code: {"name": h.name, "available_beds": ser.hospital(h)["emergency_beds_available"]}
            for h in db.scalars(select(m.Hospital))}
    return SemanticContext(available=resources.available_counts(db), hospitals=hosp,
                           max_units_per_incident=settings_store.get_constraints(db)["max_units_per_incident"])


def _save_compilation(db: Session, result: dict, incident_id: str | None) -> None:
    cmd = m.CompilerCommand(incident_id=incident_id, source=result["source"], valid=result["valid"], result=result)
    cmd.tokens = [m.CompilerToken(seq=i, type=t["type"], value=str(t["value"])[:128], lexeme=t["lexeme"][:128],
                                  position=t["position"]) for i, t in enumerate(result["tokens"])]
    db.add(cmd)
    db.commit()


def respond(db: Session, inc: m.Incident, st: Stages, overrides: dict | None = None, injured: int = 0) -> dict:
    """Run every post-compilation stage for an existing incident. Returns the partial PipelineResult."""
    ov = overrides or {}
    out: dict = {}
    # ---- severity
    hazards = len(inc.hazards or [])
    sev_features = {"incident_type": inc.type, "people_affected": inc.people_affected, "injured": injured,
                    "exits_blocked": inc.exits_blocked or 0, "hazard_count": hazards, "hour": datetime.now().hour}
    sev_pred = ml.predict(db, "severity", sev_features, inc.id, fallback=True)
    if inc.severity_source != "USER":
        inc.severity, inc.severity_source = sev_pred["prediction"], sev_pred["source"]
    db.commit()
    st.done("severity", f"{inc.severity} ({inc.severity_source}"
            + (f", {sev_pred['confidence']:.0%} confidence)" if sev_pred["confidence"] else ")"), sev_pred)
    incidents.transition(db, inc, "CLASSIFIED", f"Severity {inc.severity}")

    # ---- resource demand
    req = {k: int(v) for k, v in (inc.requirement or {}).items()}
    demand_pred = None
    if not any(req.values()):
        demand_pred = ml.predict(db, "resource_demand", {"incident_type": inc.type, "severity": inc.severity,
                                                         "people_affected": inc.people_affected, "injured": injured,
                                                         "exits_blocked": inc.exits_blocked or 0}, inc.id, fallback=True)
        req = {k: int(demand_pred["prediction"][v]) for k, v in KIND_KEYS.items()}
        src = demand_pred["source"]
    else:
        src = "COMMAND"
    for k, key in KIND_KEYS.items():
        if ov.get(key) is not None:
            req[k] = int(ov[key])
    req = {k: req.get(k, 0) for k in resources.KINDS}
    constraints = settings_store.get_constraints(db)
    if inc.severity == "CRITICAL":
        req["AMBULANCE"] = max(req["AMBULANCE"], constraints["min_ambulances_critical"])
    inc.requirement = req
    db.commit()
    st.done("resource_prediction", ", ".join(f"{v} {resources.LABEL[k]}" for k, v in req.items() if v) + f" ({src})",
            {"requirement": req, "source": src, "prediction": demand_pred})
    incidents.transition(db, inc, "ASSESSING", "Requirement estimated")
    incidents.transition(db, inc, "RESOURCE_CHECK", "Checking availability")
    out["predictions"] = [p for p in [sev_pred, demand_pred] if p]

    # ---- allocation (with state-space fallback on shortage)
    alloc = resources.allocate(db, inc, req, commit=True)
    if alloc["feasible"]:
        incidents.transition(db, inc, "DISPATCHED", "All requested units committed")
        st.done("allocation", f"{len(alloc['assigned'])} units dispatched", alloc)
    else:
        incidents.transition(db, inc, "RESOURCE_UNAVAILABLE", "; ".join(s["suggestion"] for s in alloc["shortages"]))
        incidents.transition(db, inc, "ALTERNATIVE_SEARCH", "State-space search for a reduced allocation")
        reduced = {k: min(req[k], alloc["available"][k]) for k in resources.KINDS}
        search = state_space.search(reduced, alloc["etas_by_kind"], "astar", constraints["max_units_per_incident"], 2000)
        if search["best"] and sum(reduced.values()) > 0:
            original_shortages = alloc["shortages"]
            alloc = resources.allocate(db, inc, search["best"]["config"], commit=True)
            alloc["shortages"] = original_shortages
            alloc["alternative"] = {"config": search["best"]["config"], "states_explored": search["states_explored"]}
            incidents.transition(db, inc, "DISPATCHED", "Alternative (reduced) allocation found")
            st.done("allocation", f"Shortage - alternative of {len(alloc['assigned'])} units dispatched", alloc, "warning")
        else:
            incidents.transition(db, inc, "ESCALATED", "No feasible alternative - mutual aid requested")
            st.done("allocation", "No units available - escalated", alloc, "error")
    out["allocation"] = alloc

    # ---- routing (fastest unit -> scene)
    g = graph_service.get_graph(db)
    route = None
    if alloc["assigned"]:
        first = min(alloc["assigned"], key=lambda a: a["eta_s"])
        sn = g.nodes[first["source_node"]]
        route = g.route_points((sn.lat, sn.lon), (inc.lat, inc.lon), "astar")
        route["label"] = f"{first['code']} -> {inc.location_name or inc.title}"
        dij = g.route_points((sn.lat, sn.lon), (inc.lat, inc.lon), "dijkstra")
        db.add(m.Route(incident_id=inc.id, purpose="DISPATCH", algorithm="astar", path=route["path"],
                       geometry=route["geometry"], distance_m=route["distance_m"], travel_time_s=route["travel_time_s"],
                       nodes_expanded=route["nodes_expanded"], label=route["label"]))
        db.commit()
        incidents.transition(db, inc, "ROUTING", "A* route computed")
        st.done("routing", f"{route['distance_m'] / 1000:.2f} km, {route['travel_time_s'] / 60:.1f} min "
                           f"(A* expanded {route['nodes_expanded']} vs Dijkstra {dij['nodes_expanded']})",
                {k: v for k, v in route.items() if k != "expanded"})
    out["route"] = route

    # ---- hospital
    patients = hospitals.estimate_patients(inc.type, inc.severity, inc.people_affected, injured)
    ranking = hospitals.rank(db, inc.lat, inc.lon, patients, inc.type)
    best_h = next((h for h in ranking if h["feasible"]), None)
    if best_h:
        inc.hospital_id = best_h["hospital"]["id"]
        db.commit()
        if inc.state == "ROUTING":
            incidents.transition(db, inc, "HOSPITAL_ALLOCATION", best_h["hospital"]["name"])
        st.done("hospital", f"{best_h['hospital']['name']} (score {best_h['score']:.2f}, ~{patients} patients)",
                {"selected": best_h["hospital"], "patients": patients})
    else:
        st.done("hospital", "No feasible hospital", {}, "error")
    out["hospital_ranking"] = ranking

    # ---- decision
    dec = decision_svc.generate(db, inc)
    sel = next(s for s in dec["strategies"] if s["id"] == dec["selected_id"])
    st.done("decision", f"Strategy {sel['id']} selected (score {sel['score']:.2f})",
            {"selected_id": dec["selected_id"], "reasons": dec["reasons"]})
    out["decision"] = {k: v for k, v in dec.items() if k != "hospital_ranking"}
    out["fsm"] = fsm_status(db, inc)
    st.items["fsm"].update(status="ok", summary=" -> ".join(h["to_state"] for h in out["fsm"]["history"][-4:]),
                           output=out["fsm"])

    out["response_plan"] = {
        "incident_id": inc.id, "incident_label": inc.title, "priority": inc.severity, "resources": req,
        "units": [a["code"] for a in alloc["assigned"]],
        "route_label": route["label"] if route else None, "route_distance_m": route["distance_m"] if route else None,
        "predicted_response_time_s": max((a["eta_s"] for a in alloc["assigned"]), default=None),
        "hospital": {"id": best_h["hospital"]["id"], "name": best_h["hospital"]["name"]} if best_h else None,
        "evacuation_required": bool(ov.get("evacuate")) or (inc.exits_blocked or 0) > 0 or inc.severity == "CRITICAL",
        "traffic_control": "Emergency Priority Corridor" if inc.severity in ("HIGH", "CRITICAL") else "Standard",
        "confidence": dec["confidence"], "confidence_note": dec["confidence_note"],
    }
    log_event(db, "RESPONSE_PLAN", f"Plan: {len(alloc['assigned'])} units, hospital "
              f"{best_h['hospital']['name'] if best_h else 'none'}", inc.id, decision=f"Strategy {dec['selected_id']}",
              confidence=dec["confidence"])
    return out


def fsm_status(db: Session, inc: m.Incident) -> dict:
    hist = list(db.scalars(select(m.StateTransition).where(m.StateTransition.incident_id == inc.id)
                           .order_by(m.StateTransition.id)))
    history = [{"from_state": h.from_state, "to_state": h.to_state, "event": h.event, "timestamp": ser.iso(h.timestamp),
                "reason": h.reason} for h in hist]
    return {"current": inc.state, "previous": hist[-1].from_state if hist else None,
            "allowed_next": fsm.allowed_next(inc.state), "history": history,
            "completed": list(dict.fromkeys(h["to_state"] for h in history))}


def run(db: Session, text: str, overrides: dict | None = None, auto_simulate: bool = False, speed: float = 5,
        incident_id: str | None = None) -> dict:
    ov = {k: v for k, v in (overrides or {}).items() if v not in (None, "")}
    st = Stages()
    result = compile_command(text, semantic_context(db), ov)
    t = result["timings_ms"]
    st.done("lexical", f"{len(result['tokens'])} tokens", {"tokens": result["tokens"]},
            "warning" if result["lex_warnings"] else "ok", t.get("lexical", 0))
    st.done("parsing", "Parse tree built" if result["parse"]["valid"] else f"{len(result['parse']['errors'])} syntax error(s)",
            {"errors": result["parse"]["errors"]}, "ok" if result["parse"]["valid"] else "error", t.get("parsing", 0))
    sem = result["semantic"] or {}
    if result["parse"]["valid"]:
        st.done("semantic", f"{len(sem.get('errors', []))} errors, {len(sem.get('warnings', []))} warnings",
                {"errors": sem.get("errors"), "warnings": sem.get("warnings")},
                "error" if sem.get("errors") else ("warning" if sem.get("warnings") else "ok"), t.get("semantic", 0))
    if result["ir"] is not None:
        st.done("ir", f"{len(result['execution_plan'])}-step execution plan", {"ir_text": result["ir_text"]},
                "ok" if result["valid"] else "warning", t.get("ir", 0))

    base = {"incident_id": None, "success": False, "compilation": result, "predictions": [], "fsm": None,
            "allocation": None, "route": None, "hospital_ranking": [], "decision": None, "response_plan": None,
            "simulation_run_id": None}
    if not result["valid"]:
        _save_compilation(db, result, None)
        return {**base, "stages": st.list()}

    ir = result["ir"]["INCIDENT"]
    res = result["ir"]["RESOURCES"]
    req = {"AMBULANCE": res["ambulances"], "FIRE_TRUCK": res["fire_trucks"], "POLICE": res["police_units"],
           "RESCUE": res["rescue_teams"]} if res["source"] == "COMMAND" else {}
    st.start()
    if incident_id:
        inc = incidents.get_incident(db, incident_id)
        inc.command_text = text
    else:
        inc = incidents.create_incident(db, {
            "type": ir["type"], "location_name": ir["location_name"] or ir["location"], "lat": ir["lat"], "lon": ir["lon"],
            "people_affected": ir["affected_people"], "severity_estimate": ir["severity"],
            "exits_blocked": ir["exits_blocked"], "hazards": ir["hazards"], "requirement": req,
            "description": text}, command_text=text, severity_source="USER")
    _save_compilation(db, result, inc.id)
    out = respond(db, inc, st, ov, injured=ir.get("injured") or 0)

    sim_id = None
    if auto_simulate and inc.status == "ACTIVE" and out["allocation"]["assigned"]:
        from app.simulation.engine import manager
        sim_id = manager.start(db, inc.id, speed)
        st.done("simulation", f"Simulation {sim_id} started at {speed}x", {"run_id": sim_id})
    st.done("plan", f"{inc.id}: {len(out['response_plan']['units'])} units, priority {inc.severity}", out["response_plan"])
    bus.publish("pipeline_completed", {"incident_id": inc.id}, inc.id)
    return {**base, **out, "incident_id": inc.id, "success": True, "simulation_run_id": sim_id, "stages": st.list()}
