"""Incident lifecycle as a Deterministic Finite Automaton.

M = (Q, Σ, δ, q0, F)
  Q  = STATES
  Σ  = events (ALPHABET)
  δ  = TRANSITIONS  (partial function Q × Σ → Q; undefined pairs are rejected)
  q0 = DETECTED
  F  = {RESOLVED, CANCELLED}
"""
from __future__ import annotations

from collections import deque

STATES: list[dict] = [
    {"id": "DETECTED", "label": "Incident Detected", "kind": "initial",
     "description": "An emergency has been reported (form, NL command or sensor).",
     "entry_condition": "Incident record created", "exit_condition": "Incident type and severity classified"},
    {"id": "CLASSIFIED", "label": "Incident Classified", "kind": "normal",
     "description": "Incident type confirmed and severity classified (ML model or transparent rules).",
     "entry_condition": "Severity label assigned", "exit_condition": "Assessment of needs started"},
    {"id": "ASSESSING", "label": "Resources Required", "kind": "normal",
     "description": "Resource demand is estimated from the command and the demand model.",
     "entry_condition": "Severity known", "exit_condition": "Requirement vector (ambulances, fire, police, rescue) fixed"},
    {"id": "RESOURCE_CHECK", "label": "Resource Check", "kind": "normal",
     "description": "Requirement is compared with currently available units.",
     "entry_condition": "Requirement vector fixed", "exit_condition": "Allocation feasible or shortage detected"},
    {"id": "DISPATCHED", "label": "Dispatch", "kind": "normal",
     "description": "Units are committed to the incident.",
     "entry_condition": "Feasible allocation committed", "exit_condition": "Routes computed for all units"},
    {"id": "ROUTING", "label": "Route Optimization", "kind": "normal",
     "description": "Shortest-time routes computed with A*/Dijkstra on the weighted road graph (re-entered on traffic changes).",
     "entry_condition": "Units dispatched", "exit_condition": "Destination hospital chosen"},
    {"id": "HOSPITAL_ALLOCATION", "label": "Hospital Allocation", "kind": "normal",
     "description": "Hospitals ranked by capacity, travel time and specialisation.",
     "entry_condition": "Routes available", "exit_condition": "First unit on scene"},
    {"id": "ACTIVE_RESPONSE", "label": "Active Response", "kind": "normal",
     "description": "Units on scene; patients treated and transported.",
     "entry_condition": "Units arrived", "exit_condition": "All patients transported / hazard contained"},
    {"id": "RESOLVED", "label": "Incident Resolved", "kind": "final",
     "description": "Incident closed; resources released.", "entry_condition": "Operator/simulation confirms resolution",
     "exit_condition": "— (accepting state)"},
    {"id": "RESOURCE_UNAVAILABLE", "label": "Resource Unavailable", "kind": "exception",
     "description": "The requirement exceeds available units.", "entry_condition": "Shortage detected in RESOURCE_CHECK",
     "exit_condition": "Alternative search started"},
    {"id": "ALTERNATIVE_SEARCH", "label": "Alternative Search", "kind": "exception",
     "description": "State-space search for a feasible reduced / substituted allocation.",
     "entry_condition": "Shortage", "exit_condition": "Alternative found, or none exists"},
    {"id": "ESCALATED", "label": "Escalated", "kind": "exception",
     "description": "Escalated to higher command / mutual aid from neighbouring districts.",
     "entry_condition": "No feasible alternative or situation worsened", "exit_condition": "Mutual aid granted"},
    {"id": "CANCELLED", "label": "Cancelled", "kind": "final",
     "description": "False alarm or duplicate report.", "entry_condition": "Operator cancels", "exit_condition": "— (accepting state)"},
]

TRANSITIONS: list[tuple[str, str, str]] = [
    ("DETECTED", "classify", "CLASSIFIED"),
    ("CLASSIFIED", "assess", "ASSESSING"),
    ("ASSESSING", "check_resources", "RESOURCE_CHECK"),
    ("ASSESSING", "escalate", "ESCALATED"),
    ("RESOURCE_CHECK", "resources_ok", "DISPATCHED"),
    ("RESOURCE_CHECK", "resources_short", "RESOURCE_UNAVAILABLE"),
    ("RESOURCE_UNAVAILABLE", "search_alternative", "ALTERNATIVE_SEARCH"),
    ("ALTERNATIVE_SEARCH", "alternative_found", "DISPATCHED"),
    ("ALTERNATIVE_SEARCH", "no_alternative", "ESCALATED"),
    ("ESCALATED", "mutual_aid", "RESOURCE_CHECK"),
    ("DISPATCHED", "route", "ROUTING"),
    ("ROUTING", "reroute", "ROUTING"),
    ("ROUTING", "allocate_hospital", "HOSPITAL_ALLOCATION"),
    ("HOSPITAL_ALLOCATION", "units_on_scene", "ACTIVE_RESPONSE"),
    ("ACTIVE_RESPONSE", "reroute", "ACTIVE_RESPONSE"),
    ("ACTIVE_RESPONSE", "escalate", "ESCALATED"),
    ("ACTIVE_RESPONSE", "resolve", "RESOLVED"),
]
_NON_FINAL = [s["id"] for s in STATES if s["kind"] != "final"]
TRANSITIONS += [(s, "cancel", "CANCELLED") for s in _NON_FINAL]

INITIAL = "DETECTED"
FINALS = {"RESOLVED", "CANCELLED"}
STATE_IDS = [s["id"] for s in STATES]
ALPHABET = sorted({e for _, e, _ in TRANSITIONS})

DELTA: dict[tuple[str, str], str] = {}
for q, a, p in TRANSITIONS:
    assert (q, a) not in DELTA, f"non-deterministic transition {q},{a}"
    DELTA[(q, a)] = p


class InvalidTransition(Exception):
    pass


def step(state: str, event: str) -> str:
    try:
        return DELTA[(state, event)]
    except KeyError:
        raise InvalidTransition(f"δ({state}, {event}) is undefined") from None


def event_for(from_state: str, to_state: str) -> str:
    for (q, a), p in DELTA.items():
        if q == from_state and p == to_state:
            return a
    raise InvalidTransition(f"No transition {from_state} → {to_state}; allowed: {allowed_next(from_state)}")


def allowed_next(state: str) -> list[str]:
    return list(dict.fromkeys(p for (q, _), p in DELTA.items() if q == state))


def run(events: list[str], start: str = INITIAL) -> dict:
    """Simulate the DFA on an input string of events (language acceptance)."""
    trace, q = [], start
    for a in events:
        nxt = DELTA.get((q, a))
        trace.append({"state": q, "event": a, "next": nxt})
        if nxt is None:
            return {"accepted": False, "trace": trace, "final_state": q,
                    "error": f"No transition from {q} on '{a}'. Allowed events: {[e for (s, e) in DELTA if s == q]}"}
        q = nxt
    return {"accepted": q in FINALS, "trace": trace, "final_state": q, "error": None}


def reachability(start: str) -> dict:
    """BFS over the transition graph: the set of states reachable from `start`."""
    if start not in STATE_IDS:
        raise KeyError(start)
    seen, order, dq = {start}, [start], deque([start])
    while dq:
        q = dq.popleft()
        for p in allowed_next(q):
            if p not in seen:
                seen.add(p)
                order.append(p)
                dq.append(p)
    return {"from_state": start, "reachable": order, "bfs_order": order,
            "unreachable": [s for s in STATE_IDS if s not in seen], "can_reach_final": bool(seen & FINALS)}


def main_path() -> list[str]:
    return ["DETECTED", "CLASSIFIED", "ASSESSING", "RESOURCE_CHECK", "DISPATCHED", "ROUTING",
            "HOSPITAL_ALLOCATION", "ACTIVE_RESPONSE", "RESOLVED"]


def describe() -> dict:
    return {"states": STATES, "transitions": [{"from": q, "to": p, "event": a} for q, a, p in TRANSITIONS],
            "initial": INITIAL, "finals": sorted(FINALS), "alphabet": ALPHABET}
