"""Lexical analyzer for the RESQ emergency command language.

Each token class is defined by a regular expression (a regular language). The scanner
implements the classic *maximal munch* rule: at every input position all patterns are
tried and the longest match wins; ties are broken by the declaration order below
(earlier = higher priority). E.g. ``fire trucks`` lexes as RESOURCE, not
INCIDENT_TYPE + WORD, because the RESOURCE match is longer.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.services.city_data import HOSPITAL_ALIASES, LOCATION_ALIASES

NUMBER_WORDS = {
    "zero": 0, "one": 1, "a single": 1, "single": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100, "a hundred": 100,
    "thousand": 1000, "a thousand": 1000, "a dozen": 12, "dozen": 12, "a couple of": 2, "couple of": 2,
}

INCIDENT_TYPES = {
    "FIRE": ["fire", "blaze", "fire outbreak", "burning", "flames"],
    "ACCIDENT": ["accident", "collision", "crash", "pile-up", "pileup", "multi-vehicle accident", "road accident"],
    "MEDICAL": ["medical emergency", "medical", "cardiac arrest", "heart attack", "stroke", "unconscious person"],
    "FLOOD": ["flood", "flooding", "floods", "waterlogging", "inundation"],
    "EARTHQUAKE": ["earthquake", "tremor", "tremors", "quake", "building collapse", "structural collapse"],
    "CHEMICAL_HAZARD": ["chemical hazard", "chemical leak", "gas leak", "chemical spill", "toxic leak", "hazmat"],
    "CRIME": ["crime", "robbery", "shooting", "assault", "riot", "armed attack", "theft"],
    "MISSING_PERSON": ["missing person", "missing child", "missing people", "lost child"],
}

RESOURCES = {
    "AMBULANCE": ["ambulance", "ambulances", "medical unit", "medical units", "paramedic", "paramedics", "ems unit", "ems units"],
    "FIRE_TRUCK": ["fire truck", "fire trucks", "fire engine", "fire engines", "fire tender", "fire tenders", "fire unit", "fire units", "fire brigade"],
    "POLICE": ["police", "police unit", "police units", "police car", "police cars", "police vehicle", "police vehicles", "patrol", "patrols", "police officers", "officers"],
    "RESCUE": ["rescue team", "rescue teams", "rescue unit", "rescue units", "sdrf", "ndrf", "rescuers", "divers"],
}

ACTIONS = {
    "DISPATCH": ["dispatch", "send", "deploy", "mobilize", "mobilise", "rush"],
    "REQUEST": ["need", "needs", "needed", "require", "requires", "required", "request", "requested", "requesting"],
    "EVACUATE": ["evacuate", "evacuation", "clear out"],
    "BLOCK": ["block", "close", "cordon off", "cordon", "seal off"],
    "ASSIGN": ["assign", "allocate", "admit", "transport"],
    "OPTIMIZE": ["optimize", "optimise", "reroute", "re-route"],
}

SEVERITIES = {
    "CRITICAL": ["critical", "catastrophic", "life-threatening", "extreme"],
    "HIGH": ["high", "major", "severe", "serious", "massive", "huge", "large"],
    "MEDIUM": ["medium", "moderate"],
    "LOW": ["low", "minor", "small"],
}

PERSON_NOUNS = ["people", "persons", "person", "students", "student", "children", "child", "patients", "patient",
                "victims", "victim", "casualties", "residents", "workers", "passengers", "civilians", "individuals",
                "occupants", "families", "injured people", "pupils"]

CONDITIONS = {
    "TRAFFIC_HEAVY": ["heavy traffic", "traffic jam", "congestion", "congested", "gridlock"],
    "TRAFFIC_LIGHT": ["light traffic", "clear roads"],
    "BLOCKED": ["blocked", "closed", "obstructed", "jammed"],
    "INJURED": ["injured", "hurt", "wounded"],
    "TRAPPED": ["trapped", "stuck"],
    "AFFECTED": ["affected", "involved", "at risk", "exposed", "displaced", "stranded"],
    "DEAD": ["dead", "killed", "deceased"],
    "UNCONSCIOUS": ["unconscious"],
}

HAZARDS = {
    "EXIT": ["exit", "exits", "exit routes", "staircase", "stairways"],
    "SMOKE": ["smoke", "heavy smoke"],
    "GAS": ["gas cylinder", "gas cylinders", "lpg"],
    "COLLAPSE": ["collapse", "debris", "rubble"],
    "EXPLOSION": ["explosion", "explosive", "blast"],
    "ELECTRICAL": ["power lines", "live wires", "electrical hazard", "short circuit"],
    "TOXIC": ["toxic fumes", "toxic", "fumes"],
    "WATER": ["rising water", "water level"],
    "ROAD": ["road", "roads", "bridge", "bridges"],
}

FACILITIES = ["school", "college", "hospital", "mall", "market", "factory", "building", "apartment",
              "apartments", "hotel", "office", "warehouse", "temple", "stadium", "cinema", "highway",
              "bus", "train", "residential complex", "tower"]

PREPOSITIONS = ["at", "in", "near", "to", "on", "from", "towards", "toward", "inside", "outside", "around"]
CONNECTORS = ["and", "with", "plus", "also", "along with", "as well as", "&"]
QUANTIFIERS = ["approximately", "approx", "about", "around", "nearly", "roughly", "over", "more than",
               "at least", "almost", "up to", "several", "multiple", "many", "some"]


def _alt(words) -> str:
    # Longest alternatives first so the regex engine itself prefers them.
    ws = sorted(set(words), key=len, reverse=True)
    return "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in ws)


@dataclass
class Token:
    type: str
    value: str | int
    lexeme: str
    position: int
    length: int

    def dict(self) -> dict:
        return asdict(self)


@dataclass
class TokenSpec:
    type: str
    pattern: str
    description: str
    regex: re.Pattern | None = None


def _mk(type_, pattern, desc) -> TokenSpec:
    return TokenSpec(type_, pattern, desc, re.compile(pattern, re.IGNORECASE))


_B = r"(?![A-Za-z0-9])"  # right word boundary that also works after '-' / digits

TOKEN_SPECS: list[TokenSpec] = [
    _mk("TIME", r"(?:\d{1,2}:\d{2}(?:\s?[ap]\.?m\.?)?|\d{1,2}\s?[ap]\.?m\.?" + _B + r"|immediately|right now|asap|now" + _B + r"|(?:\d+|a few)\s+minutes?\s+ago)",
        "Clock times (14:30, 2 pm) and urgency markers (now, immediately)"),
    _mk("HOSPITAL", rf"(?:{_alt(HOSPITAL_ALIASES)}){_B}", "Named hospital (Hospital A-E)"),
    _mk("LOCATION", rf"(?:{_alt(LOCATION_ALIASES)}){_B}", "Known place in the city gazetteer"),
    _mk("RESOURCE", rf"(?:{_alt(w for v in RESOURCES.values() for w in v)}){_B}", "Emergency resource class"),
    _mk("INCIDENT_TYPE", rf"(?:{_alt(w for v in INCIDENT_TYPES.values() for w in v)}){_B}", "Kind of emergency"),
    _mk("ACTION", rf"(?:{_alt(w for v in ACTIONS.values() for w in v)}){_B}", "Command verb"),
    _mk("CONDITION", rf"(?:{_alt(w for v in CONDITIONS.values() for w in v)}){_B}", "State of people / roads"),
    _mk("HAZARD", rf"(?:{_alt(w for v in HAZARDS.values() for w in v)}){_B}", "Hazard or infrastructure element"),
    _mk("SEVERITY", rf"(?:{_alt(w for v in SEVERITIES.values() for w in v)}){_B}", "Severity adjective"),
    _mk("PERSON_COUNT", rf"(?:{_alt(PERSON_NOUNS)}){_B}", "Noun counting people"),
    _mk("FACILITY", rf"(?:{_alt(FACILITIES)})s?{_B}", "Generic facility / building type"),
    _mk("QUANTITY", rf"(?:{_alt(QUANTIFIERS)}){_B}", "Quantity modifier"),
    _mk("NUMBER", rf"(?:-?\d+(?:,\d{{3}})*|(?:{_alt(NUMBER_WORDS)}){_B})", "Integer literal or number word"),
    _mk("PREPOSITION", rf"(?:{_alt(PREPOSITIONS)}){_B}", "Spatial preposition"),
    _mk("CONNECTOR", rf"(?:(?:{_alt(w for w in CONNECTORS if w != '&')}){_B}|&|,|;)", "Conjunction / list separator"),
    _mk("PUNCT", r"[.!?]+", "Sentence terminator"),
    _mk("WORD", r"[A-Za-z][A-Za-z'\-]*", "Any other word (noise, ignored by the parser)"),
]

_WS = re.compile(r"\s+")
_OTHER = re.compile(r"[^\sA-Za-z0-9]")


def _lookup(table: dict[str, list[str]], lexeme: str) -> str:
    norm = " ".join(lexeme.lower().split())
    for key, words in table.items():
        if norm in words:
            return key
    return norm.upper()


def _value(tok_type: str, lexeme: str):
    norm = " ".join(lexeme.lower().split())
    match tok_type:
        case "NUMBER":
            if norm in NUMBER_WORDS:
                return NUMBER_WORDS[norm]
            return int(norm.replace(",", ""))
        case "INCIDENT_TYPE":
            return _lookup(INCIDENT_TYPES, lexeme)
        case "RESOURCE":
            return _lookup(RESOURCES, lexeme)
        case "ACTION":
            return _lookup(ACTIONS, lexeme)
        case "SEVERITY":
            return _lookup(SEVERITIES, lexeme)
        case "CONDITION":
            return _lookup(CONDITIONS, lexeme)
        case "HAZARD":
            return _lookup(HAZARDS, lexeme)
        case "LOCATION":
            return LOCATION_ALIASES.get(norm, norm.upper().replace(" ", "_"))
        case "HOSPITAL":
            return HOSPITAL_ALIASES.get(norm, norm.upper())
        case "FACILITY":
            return norm.rstrip("s").upper() if norm not in ("bus",) else "BUS"
        case "PERSON_COUNT":
            return "PEOPLE"
        case "TIME":
            return norm.upper()
        case "QUANTITY":
            return norm.upper().replace(" ", "_")
        case _:
            return norm if tok_type in ("CONNECTOR", "PUNCT") else norm.upper()


class LexError(Exception):
    pass


def tokenize(text: str) -> tuple[list[Token], list[dict]]:
    """Scan `text` into tokens. Returns (tokens, errors). Unknown characters are
    reported as lexical warnings and skipped (the scanner never aborts silently)."""
    tokens: list[Token] = []
    errors: list[dict] = []
    pos, n = 0, len(text)
    while pos < n:
        ws = _WS.match(text, pos)
        if ws:
            pos = ws.end()
            continue
        best: tuple[int, int, TokenSpec] | None = None  # (length, -priority, spec)
        for prio, spec in enumerate(TOKEN_SPECS):
            m = spec.regex.match(text, pos)
            if m and m.end() > pos:
                cand = (m.end() - pos, -prio, spec)
                if best is None or cand[:2] > best[:2]:
                    best = cand
        if best is None:
            ch = _OTHER.match(text, pos)
            lexeme = ch.group(0) if ch else text[pos]
            errors.append({
                "phase": "LEXICAL", "severity": "WARNING", "position": pos, "found": lexeme,
                "message": f"Unrecognised character '{lexeme}' at position {pos} was ignored",
                "expected": None, "suggestion": None,
            })
            pos += len(lexeme)
            continue
        length, _, spec = best
        lexeme = text[pos:pos + length]
        tokens.append(Token(spec.type, _value(spec.type, lexeme), lexeme, pos, length))
        pos += length
    tokens.append(Token("EOF", "", "", n, 0))
    return tokens, errors


def token_specs() -> list[dict]:
    return [{"type": s.type, "pattern": s.pattern if len(s.pattern) < 400 else s.pattern[:400] + "…",
             "description": s.description} for s in TOKEN_SPECS]


def regex_accepts(token_type: str, text: str) -> dict:
    """Does `text` belong to the regular language of `token_type`? (full match)"""
    spec = next((s for s in TOKEN_SPECS if s.type == token_type), None)
    if spec is None:
        raise KeyError(token_type)
    m = spec.regex.fullmatch(text.strip())
    return {"token_type": token_type, "pattern": spec.pattern, "accepted": bool(m), "match": m.group(0) if m else None}
