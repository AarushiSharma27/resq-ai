"""Semantic analysis: syntax-directed translation of the parse tree into a symbol
table + facts, followed by static checks against the *current world state*
(resource availability, hospital capacity, gazetteer, operational constraints).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.compiler.parser import Node
from app.services.city_data import GAZETTEER

RESOURCE_KINDS = ("AMBULANCE", "FIRE_TRUCK", "POLICE", "RESCUE")
SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
VALID_TYPES = {"FIRE", "ACCIDENT", "MEDICAL", "FLOOD", "EARTHQUAKE", "CHEMICAL_HAZARD", "CRIME", "MISSING_PERSON", "OTHER"}


@dataclass
class SemanticContext:
    available: dict[str, int] = field(default_factory=lambda: {k: 0 for k in RESOURCE_KINDS})
    hospitals: dict[str, dict] = field(default_factory=dict)  # code -> {name, available_beds}
    max_units_per_incident: int = 30
    max_people: int = 1_000_000


@dataclass
class Facts:
    incident_type: str | None = None
    incident_types: list[str] = field(default_factory=list)
    severity: str | None = None
    locations: list[str] = field(default_factory=list)
    facilities: list[str] = field(default_factory=list)
    affected: int | None = None
    affected_approx: bool = False
    injured: int = 0
    trapped: int = 0
    exits_blocked: int = 0
    roads_blocked: int = 0
    hazards: list[str] = field(default_factory=list)
    traffic: str | None = None
    time: str | None = None
    resources: dict[str, int] = field(default_factory=lambda: {k: 0 for k in RESOURCE_KINDS})
    resources_mentioned: bool = False
    negative_requests: list[tuple[str, int]] = field(default_factory=list)
    hospital: str | None = None
    hospital_generic: bool = False
    evacuate: bool = False
    block_road: str | None = None
    optimize: bool = False
    dispatch: bool = False
    target: str | None = None


def _err(message, severity="ERROR", **kw) -> dict:
    return {"phase": "SEMANTIC", "severity": severity, "message": message, "position": kw.get("position"),
            "found": kw.get("found"), "expected": kw.get("expected"), "suggestion": kw.get("suggestion"),
            "code": kw.get("code")}


def _terminals(node: Node) -> list[Node]:
    if node.kind == "terminal":
        return [node]
    out: list[Node] = []
    for c in node.children:
        out.extend(_terminals(c))
    return out


class Translator:
    """Walks the parse tree (post-order attribute evaluation) collecting Facts."""

    def __init__(self):
        self.f = Facts()

    def visit(self, node: Node) -> None:
        handler = getattr(self, f"v_{node.label}", None)
        if handler:
            handler(node)
        else:
            for c in node.children:
                self.visit(c)

    # --- clauses
    def v_INCIDENT_CLAUSE(self, n: Node):
        for c in n.children:
            if c.label == "INCIDENT_TYPE":
                self.f.incident_types.append(c.value)
                self.f.incident_type = self.f.incident_type or c.value
            elif c.label == "SEVERITY":
                self._severity(c.value)
            else:
                self.visit(c)

    def v_INFO_CLAUSE(self, n: Node):
        for c in n.children:
            if c.label == "SEVERITY":
                self._severity(c.value)
            elif c.label == "CONDITION":
                self._condition(c.value, None)
            else:
                self.visit(c)

    def _severity(self, sev: str):
        if self.f.severity is None or SEVERITY_ORDER.index(sev) > SEVERITY_ORDER.index(self.f.severity):
            self.f.severity = sev

    def _condition(self, cond: str, count: int | None):
        if cond == "TRAFFIC_HEAVY":
            self.f.traffic = "HEAVY"
        elif cond == "TRAFFIC_LIGHT":
            self.f.traffic = "LOW"
        elif cond == "INJURED":
            self.f.injured += count or 1
        elif cond == "TRAPPED":
            self.f.trapped += count or 1
            self.f.hazards.append("TRAPPED")

    def v_COUNT_PHRASE(self, n: Node):
        num = next((c.value for c in n.children if c.label == "NUMBER"), None)
        approx = any(c.label == "QUANTITY" for c in n.children)
        cond = next((c.value for c in n.children if c.label == "CONDITION"), "AFFECTED")
        count = num if num is not None else 1
        if num is not None and num < 0:
            self.f.negative_requests.append(("people", num))
        if self.f.affected is None or count > self.f.affected:
            self.f.affected = count
            self.f.affected_approx = approx
        self._condition(cond, count)

    def v_HAZARD_PHRASE(self, n: Node):
        num = next((c.value for c in n.children if c.label == "NUMBER"), None)
        hz = next(c.value for c in n.children if c.label == "HAZARD")
        cond = next((c.value for c in n.children if c.label == "CONDITION"), None)
        many = any(c.label == "QUANTITY" for c in n.children)
        count = num if num is not None else (2 if many else 1)
        if hz == "EXIT" and cond == "BLOCKED":
            self.f.exits_blocked += count
            self.f.hazards.append(f"{count} exit(s) blocked")
        elif hz == "ROAD" and cond == "BLOCKED":
            self.f.roads_blocked += count
            self.f.hazards.append(f"{count} road(s) blocked")
        else:
            self.f.hazards.append(hz if not cond else f"{hz} {cond}".lower())
        if cond == "TRAPPED":
            self.f.hazards.append("TRAPPED")

    def v_DISPATCH_ACTION(self, n: Node):
        self.f.dispatch = True
        for c in n.children:
            if c.label == "TARGET":
                self._target(c)
            elif c.label != "ACTION":
                self.visit(c)

    def v_REQUEST_CLAUSE(self, n: Node):
        self.f.dispatch = True
        for c in n.children:
            self.visit(c)

    def v_RESOURCE_ITEM(self, n: Node):
        kind = next(c.value for c in n.children if c.label == "RESOURCE")
        num = next((c.value for c in n.children if c.label == "NUMBER"), None)
        count = 1 if num is None else num
        if count < 0:
            self.f.negative_requests.append((kind, count))
            return
        self.f.resources[kind] += count
        self.f.resources_mentioned = True

    def v_EVACUATE_ACTION(self, n: Node):
        self.f.evacuate = True
        for c in n.children:
            self.visit(c)

    def v_BLOCK_ACTION(self, n: Node):
        locs = [t.value for t in _terminals(n) if t.label == "LOCATION"]
        self.f.block_road = locs[0] if locs else "INCIDENT_PERIMETER"

    def v_ASSIGN_ACTION(self, n: Node):
        for c in n.children:
            if c.label == "TARGET":
                self._target(c)
            elif c.label == "HOSPITAL_REF":
                self._hospital(c)
            elif c.label == "COUNT_PHRASE":
                pass  # patients to transport — covered by affected/injured counts
            elif c.label != "ACTION":
                self.visit(c)

    def v_OPTIMIZE_ACTION(self, n: Node):
        self.f.optimize = True

    def _target(self, n: Node):
        for c in n.children:
            if c.label == "HOSPITAL_REF":
                self._hospital(c)
            elif c.label == "PLACE":
                self.v_PLACE(c)
                t = c.children[0]
                self.f.target = t.value

    def _hospital(self, n: Node):
        t = n.children[0]
        if t.label == "HOSPITAL":
            self.f.hospital = t.value
        else:
            self.f.hospital_generic = True

    def v_PLACE(self, n: Node):
        t = n.children[0]
        if t.label == "LOCATION":
            self.f.locations.append(t.value)
        else:
            self.f.facilities.append(t.value)

    def v_TIME_PHRASE(self, n: Node):
        self.f.time = next(c.value for c in n.children if c.label == "TIME")


LOCATION_SPECIFICITY = {"SCHOOL": 0, "INDUSTRIAL": 1, "TRANSIT": 1, "HERITAGE_MARKET": 1, "PUBLIC_SPACE": 1,
                        "COMMERCIAL": 2, "RESIDENTIAL": 2, "HIGHWAY": 3, "CITY": 9}


def resolve_location(keys: list[str]) -> str | None:
    known = [k for k in keys if k in GAZETTEER]
    if not known:
        return None
    return min(known, key=lambda k: (LOCATION_SPECIFICITY.get(GAZETTEER[k][3], 5), keys.index(k)))


def analyze(tree: Node, ctx: SemanticContext, overrides: dict | None = None) -> dict:
    tr = Translator()
    tr.visit(tree)
    f = tr.f
    errors: list[dict] = []
    warnings: list[dict] = []
    ov = {k: v for k, v in (overrides or {}).items() if v is not None and v != ""}

    # ---- apply user edits (from the Command Interpreter form) before validation
    if "incident_type" in ov:
        f.incident_type = str(ov["incident_type"]).upper()
    if "severity" in ov:
        f.severity = str(ov["severity"]).upper()
    if "affected_people" in ov:
        f.affected = int(ov["affected_people"])
    for key, kind in (("ambulances", "AMBULANCE"), ("fire_trucks", "FIRE_TRUCK"), ("police", "POLICE"), ("rescue", "RESCUE")):
        if key in ov:
            f.resources[kind] = int(ov[key])
            f.resources_mentioned = True
            if int(ov[key]) < 0:
                f.negative_requests.append((kind, int(ov[key])))
                f.resources[kind] = 0
    location_key: str | None
    if "location" in ov:
        cand = str(ov["location"]).strip().upper().replace(" ", "_").replace("-", "_")
        location_key = cand if cand in GAZETTEER else None
        if location_key is None:
            errors.append(_err(f"Unknown location '{ov['location']}'", code="UNKNOWN_LOCATION",
                               suggestion="Pick a location known to the city gazetteer"))
    else:
        location_key = resolve_location(f.locations)

    # ---- checks
    if f.incident_type is None:
        warnings.append(_err("No incident type stated; defaulting to OTHER", "WARNING", code="NO_INCIDENT_TYPE",
                             suggestion="Mention the emergency, e.g. 'Fire at School A'"))
        f.incident_type = "OTHER"
    elif f.incident_type not in VALID_TYPES:
        errors.append(_err(f"Unknown incident type '{f.incident_type}'", code="BAD_TYPE", expected=sorted(VALID_TYPES)))
    if len(set(f.incident_types)) > 1:
        warnings.append(_err(f"Multiple incident types mentioned ({', '.join(dict.fromkeys(f.incident_types))}); "
                             f"primary type = {f.incident_types[0]}", "WARNING", code="MULTI_TYPE"))
    if f.severity is not None and f.severity not in SEVERITY_ORDER:
        errors.append(_err(f"Invalid severity '{f.severity}'", code="BAD_SEVERITY", expected=SEVERITY_ORDER))

    if location_key is None and "location" not in ov:
        unknown = [k for k in f.locations if k not in GAZETTEER]
        if unknown:
            errors.append(_err(f"Location '{unknown[0]}' is not in the city gazetteer", code="UNKNOWN_LOCATION"))
        elif f.facilities:
            errors.append(_err(f"Location is ambiguous: a {f.facilities[0].lower()} was mentioned but no known area",
                               code="AMBIGUOUS_LOCATION", suggestion="Add the area, e.g. '... in Vijay Nagar'"))
        else:
            errors.append(_err("Location missing: the command must say where the emergency is", code="NO_LOCATION",
                               suggestion="e.g. 'at Rajwada' or 'near Palasia'"))

    for what, n in f.negative_requests:
        label = what.replace("_", " ").lower()
        errors.append(_err(f"Requested {label} count cannot be negative ({n})", code="NEGATIVE_COUNT"))
    if f.affected is not None and f.affected < 0:
        errors.append(_err("Number of affected people cannot be negative", code="NEGATIVE_COUNT"))
    if f.affected is not None and f.affected > ctx.max_people:
        errors.append(_err(f"{f.affected} affected people exceeds the plausible maximum ({ctx.max_people})", code="IMPLAUSIBLE"))

    total_units = sum(f.resources.values())
    if total_units > ctx.max_units_per_incident:
        errors.append(_err(f"Requested {total_units} units exceeds the per-incident limit of {ctx.max_units_per_incident}",
                           code="CONSTRAINT_MAX_UNITS", suggestion="Reduce the request or raise the limit in Settings"))
    for kind in RESOURCE_KINDS:
        req, avail = f.resources[kind], ctx.available.get(kind, 0)
        if req > avail:
            label = {"AMBULANCE": "ambulances", "FIRE_TRUCK": "fire trucks", "POLICE": "police units", "RESCUE": "rescue teams"}[kind]
            errors.append(_err(f"Requested {req} {label} but only {avail} are currently available.",
                               code="RESOURCE_UNAVAILABLE", found=str(req), expected=[f"<= {avail}"],
                               suggestion="Search alternative resource allocation (reduce the request or allow mutual aid)"))

    if f.hospital is not None:
        h = ctx.hospitals.get(f.hospital)
        if h is None:
            errors.append(_err(f"Hospital '{f.hospital}' does not exist", code="UNKNOWN_HOSPITAL"))
        else:
            patients = f.injured or (f.affected or 0)
            if patients > h["available_beds"]:
                warnings.append(_err(f"Hospital capacity is insufficient: {h['name']} has {h['available_beds']} free "
                                     f"emergency beds for ~{patients} patients", "WARNING", code="HOSPITAL_CAPACITY",
                                     suggestion="The decision engine will split patients across hospitals"))
    if f.resources_mentioned and f.resources["AMBULANCE"] == 0 and (f.injured or 0) > 0:
        warnings.append(_err(f"{f.injured} injured people reported but no ambulance requested", "WARNING", code="NO_AMBULANCE"))
    if not f.resources_mentioned:
        warnings.append(_err("No resources requested explicitly; resource demand will be predicted", "WARNING", code="PREDICT_RESOURCES"))

    # ---- symbol table
    symbols = [
        {"name": "incident.type", "kind": "INCIDENT_TYPE", "value": f.incident_type, "resolved": f.incident_type in VALID_TYPES},
        {"name": "incident.location", "kind": "LOCATION", "value": location_key, "resolved": location_key is not None},
        {"name": "incident.severity", "kind": "SEVERITY", "value": f.severity, "resolved": f.severity is not None},
        {"name": "incident.affected_people", "kind": "NUMBER", "value": f.affected, "resolved": f.affected is not None},
        {"name": "incident.injured", "kind": "NUMBER", "value": f.injured, "resolved": True},
        {"name": "incident.exits_blocked", "kind": "NUMBER", "value": f.exits_blocked, "resolved": True},
        {"name": "traffic.condition", "kind": "CONDITION", "value": f.traffic, "resolved": f.traffic is not None},
    ]
    for kind in RESOURCE_KINDS:
        symbols.append({"name": f"resources.{kind.lower()}", "kind": "RESOURCE", "value": f.resources[kind],
                        "resolved": f.resources[kind] <= ctx.available.get(kind, 0)})
    if f.hospital:
        symbols.append({"name": "target.hospital", "kind": "HOSPITAL", "value": f.hospital, "resolved": f.hospital in ctx.hospitals})
    for i, fac in enumerate(dict.fromkeys(f.facilities)):
        symbols.append({"name": f"facility[{i}]", "kind": "FACILITY", "value": fac, "resolved": True})

    return {"valid": not errors, "errors": errors, "warnings": warnings, "symbol_table": symbols,
            "facts": f, "location_key": location_key}
