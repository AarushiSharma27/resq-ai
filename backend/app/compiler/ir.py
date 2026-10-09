"""Intermediate representation + execution-plan generation (code generation stage)."""
from __future__ import annotations

from app.compiler.semantic import Facts
from app.services.city_data import GAZETTEER

EVAC_TYPES = {"FIRE", "FLOOD", "EARTHQUAKE", "CHEMICAL_HAZARD"}


def build_ir(f: Facts, location_key: str | None) -> dict:
    loc = GAZETTEER.get(location_key) if location_key else None
    facility = next(iter(f.facilities), None)
    if loc:
        name = loc[0]
        if facility and loc[3] != "SCHOOL" and facility not in ("HOSPITAL",):
            name = f"{facility.title()}, {loc[0]}"
    else:
        name = None
    evacuate = f.evacuate or (f.incident_type in EVAC_TYPES and ((f.affected or 0) >= 50 or f.exits_blocked > 0))
    return {
        "INCIDENT": {
            "type": f.incident_type,
            "location": location_key,
            "location_name": name,
            "location_type": (facility or (loc[3] if loc else None)),
            "lat": loc[1] if loc else None,
            "lon": loc[2] if loc else None,
            "severity": f.severity,
            "affected_people": f.affected if f.affected is not None else 0,
            "affected_is_estimate": f.affected_approx,
            "injured": f.injured,
            "trapped": f.trapped,
            "exits_blocked": f.exits_blocked,
            "roads_blocked": f.roads_blocked,
            "hazards": list(dict.fromkeys(f.hazards)),
            "time": f.time,
        },
        "RESOURCES": {
            "fire_trucks": f.resources["FIRE_TRUCK"],
            "ambulances": f.resources["AMBULANCE"],
            "police_units": f.resources["POLICE"],
            "rescue_teams": f.resources["RESCUE"],
            "source": "COMMAND" if f.resources_mentioned else "TO_BE_PREDICTED",
        },
        "ACTION": {
            "dispatch": f.dispatch or f.resources_mentioned,
            "evacuate": evacuate,
            "optimize_route": True,
            "allocate_hospital": True,
            "hospital": f.hospital,
            "block_road": f.block_road,
            "traffic_condition": f.traffic,
        },
    }


def _fmt(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def ir_text(ir: dict) -> str:
    inc, res, act = ir["INCIDENT"], ir["RESOURCES"], ir["ACTION"]
    lines = ["INCIDENT {"]
    for k in ("type", "location", "location_name", "severity", "affected_people", "injured", "exits_blocked", "hazards"):
        lines.append(f"  {k}: {_fmt(inc[k])}")
    lines.append("")
    lines.append("  RESOURCES {")
    for k in ("fire_trucks", "ambulances", "police_units", "rescue_teams", "source"):
        lines.append(f"    {k}: {_fmt(res[k])}")
    lines.append("  }")
    lines.append("")
    lines.append("  ACTION {")
    for k in ("dispatch", "evacuate", "optimize_route", "allocate_hospital", "hospital", "block_road", "traffic_condition"):
        lines.append(f"    {k}: {_fmt(act[k])}")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines)


def execution_plan(ir: dict) -> list[dict]:
    inc, res, act = ir["INCIDENT"], ir["RESOURCES"], ir["ACTION"]
    ops: list[tuple[str, dict]] = [
        ("CREATE_INCIDENT", {"type": inc["type"], "location": inc["location"]}),
        ("CLASSIFY_SEVERITY", {"given": inc["severity"], "method": "USER" if inc["severity"] else "ML_OR_RULES"}),
    ]
    if res["source"] == "TO_BE_PREDICTED":
        ops.append(("PREDICT_RESOURCE_DEMAND", {}))
    ops.append(("CHECK_RESOURCES", {k: res[k] for k in ("ambulances", "fire_trucks", "police_units", "rescue_teams")}))
    if act["dispatch"] or res["source"] == "TO_BE_PREDICTED":
        ops.append(("DISPATCH_UNITS", {}))
    if act["block_road"]:
        ops.append(("BLOCK_ROAD", {"target": act["block_road"]}))
    if act["evacuate"]:
        ops.append(("EVACUATE", {"area": inc["location"], "people": inc["affected_people"]}))
    ops.append(("OPTIMIZE_ROUTE", {"algorithm": "A*", "weight": "time"}))
    ops.append(("ALLOCATE_HOSPITAL", {"preferred": act["hospital"]}))
    ops.append(("GENERATE_DECISION", {}))
    ops.append(("SIMULATE_RESPONSE", {}))
    return [{"step": i + 1, "op": op, "args": args} for i, (op, args) in enumerate(ops)]
