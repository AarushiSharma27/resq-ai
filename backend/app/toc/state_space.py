"""State-space search over response configurations.

A state is a tuple (ambulances, fire_trucks, police, rescue) of units committed so far.
S0 = (0,0,0,0). An operator adds one unit of a kind; its step cost is the ETA (minutes)
of the next-nearest available unit of that kind, plus an over-provisioning penalty when
the requirement for that kind is already met. Goal states cover the requirement.

Algorithms: BFS, DFS (uninformed); UCS (= Dijkstra on the state graph) and A* with the
admissible heuristic h(s) = Σ_k max(0, req_k − s_k) · eta_k[s_k]  (units sorted by ETA,
so every remaining unit of kind k costs at least the next one's ETA).
"""
from __future__ import annotations

import heapq
import itertools
from collections import deque

KINDS = ("AMBULANCE", "FIRE_TRUCK", "POLICE", "RESCUE")
OVERPROVISION_PENALTY_MIN = 5.0


def _space(requirement: dict, etas: dict[str, list[float]], max_units: int):
    req = tuple(max(0, int(requirement.get(k, 0))) for k in KINDS)
    avail = tuple(len(etas.get(k, [])) for k in KINDS)
    cap = tuple(min(a, r + 1) for a, r in zip(avail, req))  # allow +1 surplus per kind
    et = tuple(sorted(etas.get(k, [])) for k in KINDS)

    def successors(s):
        if sum(s) >= max_units:
            return
        for i in range(len(KINDS)):
            if s[i] < cap[i]:
                cost = et[i][s[i]] / 60.0
                if s[i] >= req[i]:
                    cost += OVERPROVISION_PENALTY_MIN
                yield tuple(s[j] + (1 if j == i else 0) for j in range(len(KINDS))), round(cost, 3)

    def is_goal(s):
        return all(s[i] >= req[i] for i in range(len(KINDS)))

    def h(s):
        return round(sum(max(0, req[i] - s[i]) * (et[i][s[i]] / 60.0) for i in range(len(KINDS)) if s[i] < len(et[i])), 3)

    return req, avail, cap, successors, is_goal, h


def _cfg(s) -> dict:
    return dict(zip(KINDS, s))


def search(requirement: dict, etas: dict[str, list[float]], algorithm: str = "astar",
           max_units: int = 30, max_states: int = 5000) -> dict:
    req, avail, cap, successors, is_goal, h = _space(requirement, etas, max_units)
    start = (0, 0, 0, 0)
    ids: dict[tuple, str] = {}
    explored: list[dict] = []
    parent: dict[tuple, tuple | None] = {start: None}
    g: dict[tuple, float] = {start: 0.0}
    tie = itertools.count()

    def sid(s):
        if s not in ids:
            ids[s] = f"S{len(ids)}"
        return ids[s]

    def record(s):
        explored.append({"id": sid(s), "config": _cfg(s), "g": round(g[s], 3), "h": h(s), "f": round(g[s] + h(s), 3),
                         "parent": sid(parent[s]) if parent[s] is not None else None,
                         "feasible": is_goal(s), "order": len(explored)})

    goals: list[tuple] = []
    visited: set = set()
    algorithm = algorithm.lower()
    if algorithm in ("bfs", "dfs"):
        frontier = deque([start])
        sid(start)
        while frontier and len(explored) < max_states:
            s = frontier.popleft() if algorithm == "bfs" else frontier.pop()
            if s in visited:
                continue
            visited.add(s)
            record(s)
            if is_goal(s):
                goals.append(s)
            for nxt, c in successors(s):
                if nxt not in visited and nxt not in parent:
                    parent[nxt] = s
                    g[nxt] = g[s] + c
                    sid(nxt)
                    frontier.append(nxt)
        best = min(goals, key=lambda s: g[s]) if goals else None
    elif algorithm in ("ucs", "dijkstra", "astar", "a*"):
        informed = algorithm in ("astar", "a*")
        pq = [(h(start) if informed else 0.0, next(tie), start)]
        best = None
        while pq and len(explored) < max_states:
            _, _, s = heapq.heappop(pq)
            if s in visited:
                continue
            visited.add(s)
            record(s)
            if is_goal(s):
                goals.append(s)
                best = s
                break  # first goal popped is optimal (h admissible & consistent)
            for nxt, c in successors(s):
                ng = g[s] + c
                if nxt not in visited and ng < g.get(nxt, float("inf")):
                    g[nxt] = ng
                    parent[nxt] = s
                    heapq.heappush(pq, (ng + (h(nxt) if informed else 0.0), next(tie), nxt))
    else:
        raise ValueError(f"unknown algorithm {algorithm}")

    # Enumerate every feasible configuration in the bounded space (for reporting).
    feasible = []
    for combo in itertools.product(*[range(c + 1) for c in cap]):
        if is_goal(combo) and sum(combo) <= max_units:
            feasible.append(combo)

    path = []
    if best is not None:
        s = best
        while s is not None:
            path.append(sid(s))
            s = parent[s]
        path.reverse()

    def static_cost(s):
        # cost of committing the nearest units, independent of search order
        total = 0.0
        for i, k in enumerate(KINDS):
            e = sorted(etas.get(k, []))
            for j in range(s[i]):
                total += e[j] / 60.0 + (OVERPROVISION_PENALTY_MIN if j >= req[i] else 0)
        return round(total, 3)

    strategies = sorted(({"id": ids.get(s, "—"), "config": _cfg(s), "cost": static_cost(s)} for s in feasible),
                        key=lambda x: x["cost"])
    return {
        "algorithm": algorithm,
        "requirement": _cfg(req),
        "available": _cfg(avail),
        "states_explored": len(explored),
        "feasible_count": len(feasible),
        "best": None if best is None else {"id": sid(best), "config": _cfg(best), "cost": round(g[best], 3), "path": path},
        "explored": explored,
        "strategies": strategies[:25],
        "note": None if best is not None else "No configuration satisfies the requirement with the currently available units",
    }
