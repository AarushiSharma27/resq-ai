"""Weighted road-network graph and shortest-path algorithms (BFS, Dijkstra, A*).

Edge weight (time)     = distance / effective_speed,
effective_speed        = speed_limit / (traffic_factor * (0.75 if signal_priority else 1))
Blocked edges are removed from the adjacency relation.
A* heuristic (time)    = straight-line distance / V_MAX where V_MAX is the fastest
possible effective speed in the network → admissible and consistent.
"""
from __future__ import annotations

import heapq
import itertools
from collections import deque
from dataclasses import dataclass, field

from app.utils.geo import haversine_m

SIGNAL_PRIORITY_FACTOR = 0.75
ACCESS_SPEED_KMH = 20.0  # last-leg speed from road node to exact incident point


@dataclass
class GNode:
    id: str
    name: str
    kind: str
    lat: float
    lon: float


@dataclass
class GEdge:
    id: str
    source: str
    target: str
    name: str
    distance_m: float
    speed_kmh: float
    geometry: list[list[float]]
    traffic_level: str = "LOW"
    traffic_factor: float = 1.0
    blocked: bool = False
    accident: bool = False
    signal_priority: bool = False

    @property
    def effective_speed_kmh(self) -> float:
        f = self.traffic_factor * (SIGNAL_PRIORITY_FACTOR if self.signal_priority else 1.0)
        return self.speed_kmh / max(f, 0.1)

    @property
    def travel_time_s(self) -> float:
        return self.distance_m / (self.effective_speed_kmh / 3.6)

    def to_dict(self) -> dict:
        return {"id": self.id, "source": self.source, "target": self.target, "name": self.name,
                "distance_m": round(self.distance_m, 1), "speed_kmh": self.speed_kmh,
                "traffic_level": self.traffic_level, "traffic_factor": round(self.traffic_factor, 3),
                "blocked": self.blocked, "accident": self.accident, "signal_priority": self.signal_priority,
                "travel_time_s": round(self.travel_time_s, 1), "effective_speed_kmh": round(self.effective_speed_kmh, 1),
                "geometry": self.geometry}


@dataclass
class RoadGraph:
    nodes: dict[str, GNode] = field(default_factory=dict)
    edges: dict[str, GEdge] = field(default_factory=dict)
    adj: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # node -> [(neighbor, edge_id)]

    def add_node(self, n: GNode):
        self.nodes[n.id] = n
        self.adj.setdefault(n.id, [])

    def add_edge(self, e: GEdge):
        self.edges[e.id] = e
        self.adj.setdefault(e.source, []).append((e.target, e.id))
        self.adj.setdefault(e.target, []).append((e.source, e.id))

    @property
    def v_max_ms(self) -> float:
        top = max((e.speed_kmh for e in self.edges.values()), default=50.0)
        return top / SIGNAL_PRIORITY_FACTOR / 3.6

    # ---------------------------------------------------------------- helpers
    def weight(self, e: GEdge, mode: str) -> float:
        return e.distance_m if mode == "distance" else e.travel_time_s

    def nearest_node(self, lat: float, lon: float, kinds: tuple[str, ...] = ("intersection",)) -> str:
        cands = [n for n in self.nodes.values() if n.kind in kinds and self.adj.get(n.id)]
        return min(cands, key=lambda n: haversine_m(lat, lon, n.lat, n.lon)).id

    def heuristic(self, a: str, b: str, mode: str) -> float:
        na, nb = self.nodes[a], self.nodes[b]
        d = haversine_m(na.lat, na.lon, nb.lat, nb.lon)
        return d if mode == "distance" else d / self.v_max_ms

    def _neighbors(self, u: str):
        for v, eid in self.adj.get(u, []):
            e = self.edges[eid]
            if not e.blocked:
                yield v, e

    # ---------------------------------------------------------------- algorithms
    def dijkstra(self, s: str, t: str, mode: str = "time") -> dict:
        return self._best_first(s, t, mode, informed=False)

    def astar(self, s: str, t: str, mode: str = "time") -> dict:
        return self._best_first(s, t, mode, informed=True)

    def _best_first(self, s: str, t: str, mode: str, informed: bool) -> dict:
        tie = itertools.count()
        dist = {s: 0.0}
        prev: dict[str, tuple[str, str] | None] = {s: None}
        pq = [((self.heuristic(s, t, mode) if informed else 0.0), next(tie), s)]
        closed: set[str] = set()
        expanded: list[str] = []
        while pq:
            _, _, u = heapq.heappop(pq)
            if u in closed:
                continue
            closed.add(u)
            expanded.append(u)
            if u == t:
                break
            for v, e in self._neighbors(u):
                nd = dist[u] + self.weight(e, mode)
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = (u, e.id)
                    heapq.heappush(pq, (nd + (self.heuristic(v, t, mode) if informed else 0.0), next(tie), v))
        return self._result("astar" if informed else "dijkstra", mode, s, t, prev, expanded, t in closed)

    def single_source(self, s: str, mode: str = "time") -> dict[str, float]:
        """Dijkstra from `s` to every node (roads are two-way, so this also gives
        the cost from every node *to* `s`)."""
        dist = {s: 0.0}
        pq, done = [(0.0, s)], set()
        while pq:
            d, u = heapq.heappop(pq)
            if u in done:
                continue
            done.add(u)
            for v, e in self._neighbors(u):
                nd = d + self.weight(e, mode)
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        return dist

    def bfs(self, s: str, t: str, mode: str = "hops") -> dict:
        """Unweighted BFS: minimises the number of road segments (hops)."""
        prev: dict[str, tuple[str, str] | None] = {s: None}
        dq, expanded = deque([s]), []
        while dq:
            u = dq.popleft()
            expanded.append(u)
            if u == t:
                break
            for v, e in self._neighbors(u):
                if v not in prev:
                    prev[v] = (u, e.id)
                    dq.append(v)
        return self._result("bfs", "hops", s, t, prev, expanded, t in prev)

    def _result(self, algo, mode, s, t, prev, expanded, found) -> dict:
        if not found:
            return {"algorithm": algo, "weight": mode, "found": False, "path": [], "edges": [], "geometry": [],
                    "distance_m": None, "travel_time_s": None, "nodes_expanded": len(expanded), "expanded": expanded}
        path, edge_ids, v = [t], [], t
        while prev[v] is not None:
            u, eid = prev[v]
            edge_ids.append(eid)
            path.append(u)
            v = u
        path.reverse()
        edge_ids.reverse()
        geometry: list[list[float]] = []
        for i, eid in enumerate(edge_ids):
            e = self.edges[eid]
            pts = e.geometry if e.source == path[i] else list(reversed(e.geometry))
            geometry.extend(pts if not geometry else pts[1:])
        if not geometry:
            n = self.nodes[s]
            geometry = [[n.lat, n.lon]]
        return {"algorithm": algo, "weight": mode, "found": True, "path": path, "edges": edge_ids, "geometry": geometry,
                "distance_m": round(sum(self.edges[e].distance_m for e in edge_ids), 1),
                "travel_time_s": round(sum(self.edges[e].travel_time_s for e in edge_ids), 1),
                "nodes_expanded": len(expanded), "expanded": expanded}

    def shortest(self, s: str, t: str, algorithm: str = "astar", mode: str = "time") -> dict:
        if algorithm == "bfs":
            return self.bfs(s, t)
        if algorithm == "dijkstra":
            return self.dijkstra(s, t, mode)
        return self.astar(s, t, mode)

    def route_points(self, src: tuple[float, float], dst: tuple[float, float], algorithm: str = "astar",
                     mode: str = "time", src_kinds=("intersection", "station", "hospital"),
                     dst_kinds=("intersection", "hospital")) -> dict:
        """Route between two arbitrary coordinates: snap to nearest graph nodes and add
        straight access legs at ACCESS_SPEED_KMH."""
        s = self.nearest_node(*src, kinds=src_kinds)
        t = self.nearest_node(*dst, kinds=dst_kinds)
        r = self.shortest(s, t, algorithm, mode)
        if not r["found"]:
            return r
        ns, nt = self.nodes[s], self.nodes[t]
        leg1 = haversine_m(src[0], src[1], ns.lat, ns.lon)
        leg2 = haversine_m(nt.lat, nt.lon, dst[0], dst[1])
        access_time = (leg1 + leg2) / (ACCESS_SPEED_KMH / 3.6)
        r["geometry"] = [list(src)] + r["geometry"] + [list(dst)]
        r["distance_m"] = round(r["distance_m"] + leg1 + leg2, 1)
        if r["travel_time_s"] is not None:
            r["travel_time_s"] = round(r["travel_time_s"] + access_time, 1)
        else:  # BFS (hops) – still report a physical time estimate along the chosen path
            r["travel_time_s"] = round(sum(self.edges[e].travel_time_s for e in r["edges"]) + access_time, 1)
        return r


def node_payload(n: GNode) -> dict:
    return {"id": n.id, "name": n.name, "kind": n.kind, "lat": n.lat, "lon": n.lon}
