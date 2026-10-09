"""RESQ emergency-command compiler: lexer → parser → semantic analyzer → IR → plan."""
from __future__ import annotations

import time

from app.compiler.ir import build_ir, execution_plan, ir_text
from app.compiler.lexer import Token, regex_accepts, token_specs, tokenize
from app.compiler.parser import GRAMMAR, grammar_bnf, parse
from app.compiler.semantic import SemanticContext, analyze

__all__ = ["compile_command", "tokenize", "parse", "analyze", "SemanticContext", "grammar_info", "regex_accepts"]


def grammar_info() -> dict:
    return {
        "start": "COMMAND",
        "productions": [{"lhs": lhs, "alternatives": alts} for lhs, alts in GRAMMAR],
        "bnf": grammar_bnf(),
        "token_specs": token_specs(),
    }


def compile_command(text: str, ctx: SemanticContext, overrides: dict | None = None) -> dict:
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    tokens, lex_errors = tokenize(text)
    timings["lexical"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    tree, syntax_errors = parse(tokens)
    timings["parsing"] = (time.perf_counter() - t0) * 1000

    result: dict = {
        "source": text,
        "tokens": [t.dict() for t in tokens],
        "lex_warnings": lex_errors,
        "parse": {"valid": tree is not None, "tree": tree.to_dict() if tree else None, "errors": syntax_errors},
        "semantic": None, "ir": None, "ir_text": None, "execution_plan": [], "structured": None,
        "timings_ms": timings, "valid": False,
    }
    if tree is None:
        result["semantic"] = {"valid": False, "errors": [], "warnings": [], "symbol_table": [], "skipped": True}
        return result

    t0 = time.perf_counter()
    sem = analyze(tree, ctx, overrides)
    timings["semantic"] = (time.perf_counter() - t0) * 1000
    facts = sem.pop("facts")
    loc_key = sem.pop("location_key")
    result["semantic"] = sem

    t0 = time.perf_counter()
    ir = build_ir(facts, loc_key)
    result["ir"] = ir
    result["ir_text"] = ir_text(ir)
    result["execution_plan"] = execution_plan(ir)
    timings["ir"] = (time.perf_counter() - t0) * 1000
    result["structured"] = {
        "incident_type": ir["INCIDENT"]["type"],
        "severity": ir["INCIDENT"]["severity"],
        "location": ir["INCIDENT"]["location_name"] or ir["INCIDENT"]["location"],
        "location_key": ir["INCIDENT"]["location"],
        "affected_people": ir["INCIDENT"]["affected_people"],
        "injured": ir["INCIDENT"]["injured"],
        "ambulance_required": ir["RESOURCES"]["ambulances"],
        "fire_trucks_required": ir["RESOURCES"]["fire_trucks"],
        "police_required": ir["RESOURCES"]["police_units"],
        "rescue_required": ir["RESOURCES"]["rescue_teams"],
        "traffic_condition": ir["ACTION"]["traffic_condition"],
        "evacuate": ir["ACTION"]["evacuate"],
    }
    result["valid"] = sem["valid"]
    return result
