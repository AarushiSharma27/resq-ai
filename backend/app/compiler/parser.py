"""Recursive-descent (LL) parser for the RESQ emergency command language.

The parser consumes the *significant* tokens produced by the lexer (WORD tokens are
noise words such as "detected", "the", "are" and are filtered out before parsing) and
builds a concrete parse tree according to the grammar in ``GRAMMAR``. Syntax errors use
panic-mode recovery: the error is recorded, input is skipped to the next sentence
terminator, and parsing resumes so that several errors can be reported in one pass.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from app.compiler.lexer import Token

# ---------------------------------------------------------------- grammar (EBNF)
GRAMMAR: list[tuple[str, list[list[str]]]] = [
    ("COMMAND", [["STATEMENT", "{ [SEPARATOR] STATEMENT }", "EOF"]]),
    ("SEPARATOR", [["PUNCT"], ["CONNECTOR"]]),
    ("STATEMENT", [["INCIDENT_CLAUSE"], ["ACTION_CLAUSE"], ["REQUEST_CLAUSE"], ["INFO_CLAUSE"]]),
    ("INCIDENT_CLAUSE", [["[SEVERITY]", "INCIDENT_TYPE", "[LOCATION_PHRASE]", "[TIME_PHRASE]"]]),
    ("ACTION_CLAUSE", [["DISPATCH_ACTION"], ["EVACUATE_ACTION"], ["BLOCK_ACTION"], ["ASSIGN_ACTION"], ["OPTIMIZE_ACTION"]]),
    ("DISPATCH_ACTION", [["ACTION<DISPATCH|REQUEST>", "RESOURCE_LIST", "[TARGET]", "[TIME_PHRASE]"]]),
    ("EVACUATE_ACTION", [["ACTION<EVACUATE>", "[LOCATION_PHRASE]"]]),
    ("BLOCK_ACTION", [["ACTION<BLOCK>", "[HAZARD<ROAD>]", "[LOCATION_PHRASE]"]]),
    ("ASSIGN_ACTION", [["ACTION<ASSIGN>", "RESOURCE_LIST", "[TARGET]"],
                       ["ACTION<ASSIGN>", "[[NUMBER] PERSON_COUNT]", "[PREPOSITION]", "HOSPITAL_REF"]]),
    ("OPTIMIZE_ACTION", [["ACTION<OPTIMIZE>"]]),
    ("REQUEST_CLAUSE", [["RESOURCE_LIST", "ACTION<REQUEST>"]]),
    ("INFO_CLAUSE", [["[SEVERITY]", "COUNT_PHRASE"], ["[SEVERITY]", "HAZARD_PHRASE"], ["[SEVERITY]", "CONDITION"],
                     ["LOCATION_PHRASE"], ["TIME_PHRASE"]]),
    ("COUNT_PHRASE", [["[QUANTITY]", "[NUMBER]", "PERSON_COUNT", "[CONDITION]"]]),
    ("HAZARD_PHRASE", [["[QUANTITY]", "[NUMBER]", "HAZARD", "[CONDITION]"]]),
    ("RESOURCE_LIST", [["RESOURCE_ITEM", "{ CONNECTOR RESOURCE_ITEM }"]]),
    ("RESOURCE_ITEM", [["[QUANTITY]", "[NUMBER]", "RESOURCE"]]),
    ("TARGET", [["PREPOSITION", "PLACE"], ["PREPOSITION", "HOSPITAL_REF"]]),
    ("HOSPITAL_REF", [["HOSPITAL"], ["FACILITY<HOSPITAL>"]]),
    ("LOCATION_PHRASE", [["[PREPOSITION]", "PLACE", "{ [PREPOSITION | CONNECTOR] PLACE }"]]),
    ("PLACE", [["LOCATION"], ["FACILITY"]]),
    ("TIME_PHRASE", [["[PREPOSITION]", "TIME"]]),
]

MEANINGS: dict[str, str] = {
    "COMMAND": "Root of the program: one or more statements describing an emergency and the actions to take.",
    "STATEMENT": "A single clause of the command (incident description, action, request or extra information).",
    "INCIDENT_CLAUSE": "Declares the emergency: its type, optional severity, location and time.",
    "ACTION_CLAUSE": "An imperative instruction to the command centre.",
    "DISPATCH_ACTION": "Dispatch (or request) a list of resources, optionally to a target.",
    "EVACUATE_ACTION": "Order an evacuation of the incident area or a named place.",
    "BLOCK_ACTION": "Close a road / area to traffic.",
    "ASSIGN_ACTION": "Assign patients or units to a hospital or place.",
    "OPTIMIZE_ACTION": "Ask the engine to optimise routing / the overall response.",
    "REQUEST_CLAUSE": "Post-fix request: '<resources> required/needed'.",
    "INFO_CLAUSE": "Additional facts: people counts, hazards, road/traffic conditions, locations or time.",
    "COUNT_PHRASE": "Number of people and their condition (affected, injured, trapped...).",
    "HAZARD_PHRASE": "A hazard or infrastructure element and its condition (e.g. 2 exits blocked).",
    "RESOURCE_LIST": "One or more resource items joined by connectors.",
    "RESOURCE_ITEM": "Quantity + resource class (e.g. 3 ambulances). Missing quantity defaults to 1.",
    "TARGET": "Destination of a dispatch/assignment.",
    "HOSPITAL_REF": "Reference to a hospital (named or generic).",
    "LOCATION_PHRASE": "Where the incident is; resolved against the city gazetteer during semantic analysis.",
    "PLACE": "A gazetteer location or a generic facility type.",
    "TIME_PHRASE": "When the incident was detected / urgency.",
    "SEPARATOR": "Sentence terminator or conjunction between statements.",
    "INCIDENT_TYPE": "Terminal: the category of emergency (drives classification and resource needs).",
    "SEVERITY": "Terminal: explicit severity keyword (overrides ML prediction unless edited).",
    "LOCATION": "Terminal: known place from the gazetteer (has coordinates).",
    "FACILITY": "Terminal: generic building type; refines the location type.",
    "HOSPITAL": "Terminal: named hospital.",
    "NUMBER": "Terminal: integer literal (digits or number words).",
    "QUANTITY": "Terminal: approximate quantity modifier.",
    "RESOURCE": "Terminal: resource class (AMBULANCE, FIRE_TRUCK, POLICE, RESCUE).",
    "ACTION": "Terminal: command verb.",
    "PERSON_COUNT": "Terminal: noun that counts people.",
    "CONDITION": "Terminal: state of people or roads.",
    "HAZARD": "Terminal: hazard / infrastructure element.",
    "TIME": "Terminal: time or urgency marker.",
    "PREPOSITION": "Terminal: spatial preposition.",
    "CONNECTOR": "Terminal: conjunction / list separator.",
    "PUNCT": "Terminal: sentence terminator.",
    "EOF": "End of input.",
}


def grammar_bnf() -> str:
    lines = []
    for lhs, alts in GRAMMAR:
        rhs = "\n    | ".join(" ".join(a) for a in alts)
        lines.append(f"{lhs:<16} → {rhs}")
    lines.append("\nNotation: [X] optional, { X } zero-or-more, T<v> terminal T restricted to value v.")
    lines.append("WORD tokens (noise words) are discarded before parsing.")
    return "\n".join(lines)


@dataclass
class Node:
    label: str
    kind: str = "nonterminal"
    value: object | None = None
    lexeme: str | None = None
    position: int | None = None
    children: list["Node"] = field(default_factory=list)

    def to_dict(self, counter=None) -> dict:
        counter = counter or itertools.count()
        d = {
            "id": f"n{next(counter)}", "label": self.label, "kind": self.kind,
            "meaning": MEANINGS.get(self.label, ""), "children": [c.to_dict(counter) for c in self.children],
        }
        if self.kind == "terminal":
            d.update(value=self.value, lexeme=self.lexeme, position=self.position)
        return d


class ParseError(Exception):
    def __init__(self, message: str, token: Token, expected: list[str], suggestion: str | None = None):
        super().__init__(message)
        self.token, self.expected, self.suggestion = token, expected, suggestion

    def to_dict(self) -> dict:
        return {
            "phase": "SYNTAX", "severity": "ERROR", "message": str(self), "position": self.token.position,
            "found": f"{self.token.type}('{self.token.lexeme}')" if self.token.type != "EOF" else "end of input",
            "expected": self.expected, "suggestion": self.suggestion,
        }


STATEMENT_FIRST = {"SEVERITY", "INCIDENT_TYPE", "ACTION", "RESOURCE", "QUANTITY", "NUMBER", "PERSON_COUNT",
                   "HAZARD", "CONDITION", "PREPOSITION", "LOCATION", "FACILITY", "TIME", "HOSPITAL"}


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = [t for t in tokens if t.type != "WORD"]
        self.i = 0
        self.errors: list[dict] = []

    # --------------------------------------------------------------- helpers
    def peek(self, k: int = 0) -> Token:
        return self.tokens[min(self.i + k, len(self.tokens) - 1)]

    def at(self, type_: str, values: tuple | None = None, k: int = 0) -> bool:
        t = self.peek(k)
        return t.type == type_ and (values is None or t.value in values)

    def eat(self, type_: str, values: tuple | None = None, expected_desc: str | None = None) -> Node:
        t = self.peek()
        if self.at(type_, values):
            self.i += 1
            return Node(t.type, "terminal", t.value, t.lexeme, t.position)
        exp = expected_desc or (f"{type_}({'|'.join(values)})" if values else type_)
        raise ParseError(self._unexpected(t, exp), t, [exp])

    @staticmethod
    def _unexpected(t: Token, expected: str) -> str:
        found = "end of input" if t.type == "EOF" else f"token '{t.lexeme}' ({t.type})"
        return f"Unexpected {found} at position {t.position}; expected {expected}"

    def opt(self, type_: str, values: tuple | None = None) -> Node | None:
        return self.eat(type_, values) if self.at(type_, values) else None

    def _is_place_start(self, k: int = 0) -> bool:
        return self.at("LOCATION", k=k) or self.at("FACILITY", k=k)

    # --------------------------------------------------------------- grammar
    def parse(self) -> Node | None:
        root = Node("COMMAND")
        if self.at("EOF"):
            self.errors.append(ParseError("Empty command", self.peek(), ["STATEMENT"]).to_dict())
            return None
        while not self.at("EOF"):
            if self.at("PUNCT") or self.at("CONNECTOR"):
                root.children.append(Node("SEPARATOR", children=[self.eat(self.peek().type)]))
                continue
            try:
                root.children.append(self.statement())
            except ParseError as e:
                self.errors.append(e.to_dict())
                self._recover()
        root.children.append(Node("EOF", "terminal", "", "", self.peek().position))
        return None if self.errors else root

    def _recover(self) -> None:
        """Panic mode: skip to the token after the next sentence terminator."""
        self.i += 1
        while not self.at("EOF") and not self.at("PUNCT"):
            self.i += 1

    def statement(self) -> Node:
        t = self.peek()
        node = Node("STATEMENT")
        if t.type == "INCIDENT_TYPE" or (t.type == "SEVERITY" and self.at("INCIDENT_TYPE", k=1)):
            node.children.append(self.incident_clause())
        elif t.type == "ACTION":
            node.children.append(self.action_clause())
        elif t.type == "RESOURCE" or (t.type in ("NUMBER", "QUANTITY") and self._resource_item_ahead()):
            node.children.append(self.request_clause())
        elif t.type in STATEMENT_FIRST:
            node.children.append(self.info_clause())
        else:
            raise ParseError(self._unexpected(t, "the start of a statement"), t,
                             ["INCIDENT_TYPE", "ACTION", "NUMBER", "RESOURCE", "LOCATION", "SEVERITY"])
        return node

    def _resource_item_ahead(self) -> bool:
        k = 0
        if self.at("QUANTITY", k=k):
            k += 1
        if self.at("NUMBER", k=k):
            k += 1
        return self.at("RESOURCE", k=k)

    def incident_clause(self) -> Node:
        n = Node("INCIDENT_CLAUSE")
        if (s := self.opt("SEVERITY")):
            n.children.append(s)
        n.children.append(self.eat("INCIDENT_TYPE"))
        if self._location_phrase_ahead():
            n.children.append(self.location_phrase())
        if self._time_phrase_ahead():
            n.children.append(self.time_phrase())
        return n

    def action_clause(self) -> Node:
        verb = self.peek().value
        wrap = Node("ACTION_CLAUSE")
        if verb in ("DISPATCH", "REQUEST"):
            n = Node("DISPATCH_ACTION", children=[self.eat("ACTION")])
            if not self._resource_item_ahead():
                t = self.peek()
                raise ParseError(self._unexpected(t, "RESOURCE_QUANTITY (e.g. '2 ambulances')"), t,
                                 ["NUMBER", "RESOURCE"], "Write the resources after the verb, e.g. 'Dispatch 2 ambulances'.")
            n.children.append(self.resource_list())
            if self.at("PREPOSITION") and (self._is_place_start(1) or self.at("HOSPITAL", k=1)):
                n.children.append(self.target())
            if self._time_phrase_ahead():
                n.children.append(self.time_phrase())
        elif verb == "EVACUATE":
            n = Node("EVACUATE_ACTION", children=[self.eat("ACTION")])
            if self._location_phrase_ahead():
                n.children.append(self.location_phrase())
        elif verb == "BLOCK":
            n = Node("BLOCK_ACTION", children=[self.eat("ACTION")])
            if (h := self.opt("HAZARD", ("ROAD",))):
                n.children.append(h)
            if self._location_phrase_ahead():
                n.children.append(self.location_phrase())
        elif verb == "ASSIGN":
            n = Node("ASSIGN_ACTION", children=[self.eat("ACTION")])
            if self._resource_item_ahead():
                n.children.append(self.resource_list())
                if self.at("PREPOSITION") and (self._is_place_start(1) or self.at("HOSPITAL", k=1)):
                    n.children.append(self.target())
            else:
                if self.at("NUMBER") and self.at("PERSON_COUNT", k=1):
                    n.children.append(self.count_phrase())
                elif self.at("PERSON_COUNT"):
                    n.children.append(self.count_phrase())
                if (p := self.opt("PREPOSITION")):
                    n.children.append(p)
                n.children.append(self.hospital_ref())
        else:  # OPTIMIZE
            n = Node("OPTIMIZE_ACTION", children=[self.eat("ACTION")])
        wrap.children.append(n)
        return wrap

    def request_clause(self) -> Node:
        n = Node("REQUEST_CLAUSE", children=[self.resource_list()])
        n.children.append(self.eat("ACTION", ("REQUEST",), "ACTION(REQUEST) such as 'required' or 'needed' after a resource list"))
        return n

    def info_clause(self) -> Node:
        n = Node("INFO_CLAUSE")
        if (s := self.opt("SEVERITY")):
            n.children.append(s)
        k = 0
        while self.at("QUANTITY", k=k) or self.at("NUMBER", k=k):
            k += 1
        t = self.peek(k)
        if t.type == "PERSON_COUNT":
            n.children.append(self.count_phrase())
        elif t.type == "HAZARD":
            n.children.append(self.hazard_phrase())
        elif k == 0 and t.type == "CONDITION":
            n.children.append(self.eat("CONDITION"))
        elif k == 0 and not n.children and self._location_phrase_ahead():
            n.children.append(self.location_phrase())
        elif k == 0 and not n.children and self._time_phrase_ahead():
            n.children.append(self.time_phrase())
        else:
            bad = self.peek(k)
            exp = ["PERSON_COUNT", "HAZARD"] if k else ["INCIDENT_TYPE", "PERSON_COUNT", "HAZARD", "CONDITION"]
            raise ParseError(self._unexpected(bad, " or ".join(exp)), bad, exp)
        return n

    def count_phrase(self) -> Node:
        n = Node("COUNT_PHRASE")
        if (q := self.opt("QUANTITY")):
            n.children.append(q)
        if (num := self.opt("NUMBER")):
            n.children.append(num)
        n.children.append(self.eat("PERSON_COUNT"))
        if (c := self.opt("CONDITION")):
            n.children.append(c)
        return n

    def hazard_phrase(self) -> Node:
        n = Node("HAZARD_PHRASE")
        if (q := self.opt("QUANTITY")):
            n.children.append(q)
        if (num := self.opt("NUMBER")):
            n.children.append(num)
        n.children.append(self.eat("HAZARD"))
        if (c := self.opt("CONDITION")):
            n.children.append(c)
        return n

    def resource_list(self) -> Node:
        n = Node("RESOURCE_LIST", children=[self.resource_item()])
        while self.at("CONNECTOR"):
            save = self.i
            conn = self.eat("CONNECTOR")
            if self._resource_item_ahead():
                n.children.append(conn)
                n.children.append(self.resource_item())
            else:
                self.i = save  # connector belongs to the statement list
                break
        return n

    def resource_item(self) -> Node:
        n = Node("RESOURCE_ITEM")
        if (q := self.opt("QUANTITY")):
            n.children.append(q)
        if (num := self.opt("NUMBER")):
            n.children.append(num)
        n.children.append(self.eat("RESOURCE", expected_desc="RESOURCE (ambulance, fire truck, police unit, rescue team)"))
        return n

    def target(self) -> Node:
        n = Node("TARGET", children=[self.eat("PREPOSITION")])
        if self.at("HOSPITAL") or self.at("FACILITY", ("HOSPITAL",)):
            n.children.append(self.hospital_ref())
        else:
            n.children.append(self.place())
        return n

    def hospital_ref(self) -> Node:
        if self.at("HOSPITAL"):
            return Node("HOSPITAL_REF", children=[self.eat("HOSPITAL")])
        return Node("HOSPITAL_REF", children=[self.eat("FACILITY", ("HOSPITAL",), "HOSPITAL (e.g. 'Hospital B')")])

    def _location_phrase_ahead(self) -> bool:
        if self._is_place_start():
            return True
        # 'around'/'about' are lexed as QUANTITY but act as prepositions before a place
        return (self.at("PREPOSITION") or self.at("QUANTITY", ("AROUND",))) and self._is_place_start(1)

    def location_phrase(self) -> Node:
        n = Node("LOCATION_PHRASE")
        if self.at("PREPOSITION"):
            n.children.append(self.eat("PREPOSITION"))
        elif self.at("QUANTITY", ("AROUND",)):
            q = self.eat("QUANTITY")
            n.children.append(Node("PREPOSITION", "terminal", "around", q.lexeme, q.position))
        n.children.append(self.place())
        while True:
            if self._is_place_start():
                n.children.append(self.place())
            elif (self.at("PREPOSITION") or self.at("CONNECTOR", (",",))) and self._is_place_start(1):
                n.children.append(self.eat(self.peek().type))
                n.children.append(self.place())
            else:
                break
        return n

    def place(self) -> Node:
        if self.at("LOCATION"):
            return Node("PLACE", children=[self.eat("LOCATION")])
        return Node("PLACE", children=[self.eat("FACILITY", expected_desc="LOCATION")])

    def _time_phrase_ahead(self) -> bool:
        return self.at("TIME") or (self.at("PREPOSITION") and self.at("TIME", k=1))

    def time_phrase(self) -> Node:
        n = Node("TIME_PHRASE")
        if self.at("PREPOSITION"):
            n.children.append(self.eat("PREPOSITION"))
        n.children.append(self.eat("TIME"))
        return n


def parse(tokens: list[Token]) -> tuple[Node | None, list[dict]]:
    p = Parser(tokens)
    tree = p.parse()
    return tree, p.errors
