"""Simulated IoT sensor network (traffic counters, air quality, road status, hospital feeds).

All readings are synthetic random walks and are labelled mode=SIMULATION everywhere.
A background loop also drifts road traffic factors so routing reacts to changing conditions.
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
from collections import deque
from datetime import datetime, timezone

from sqlalchemy import select

from app import models as m
from app.database import SessionLocal
from app.services import graph_service
from app.services.bus import bus
from app.services.city_data import HOSPITALS, INTERSECTIONS

log = logging.getLogger("resq.iot")
BASE_INTERVAL_S = 5.0


class IoTSimulator:
    def __init__(self):
        self.speed = 1
        self.sensors: dict[str, dict] = {}
        self.series: dict[str, deque] = {}
        self._task: asyncio.Task | None = None
        rng = random.Random(7)
        for nid, name, lat, lon in INTERSECTIONS[::2]:
            self._add(f"TRF-{nid[2:]}", "traffic", f"Traffic counter {name}", lat, lon,
                      {"vehicles_per_min": rng.randint(20, 60), "avg_speed_kmh": rng.randint(20, 40)})
        for nid, name, lat, lon in INTERSECTIONS[1::5]:
            self._add(f"AQI-{nid[2:]}", "air_quality", f"Air quality {name}", lat + 0.002, lon + 0.002,
                      {"aqi": rng.randint(60, 140), "pm25": rng.randint(25, 80), "co_ppm": round(rng.uniform(0.3, 1.5), 2)})
        for nid, name, lat, lon in INTERSECTIONS[3::6]:
            self._add(f"RD-{nid[2:]}", "road", f"Road surface {name}", lat - 0.002, lon, {"water_level_cm": 0, "temperature_c": 31})
        self._add("EMG-CALLS", "emergency", "Emergency call volume", 22.7196, 75.8577, {"calls_per_10min": 4})
        for code, name, lat, lon, _s, (er_t, er_o, _it, _io) in HOSPITALS:
            self._add(f"HSP-{code[-1]}", "hospital", f"{name} bed feed", lat, lon,
                      {"er_occupancy_pct": round(100 * er_o / er_t, 1), "waiting_patients": rng.randint(0, 6)})

    def _add(self, sid, kind, name, lat, lon, latest):
        now = datetime.now(timezone.utc).isoformat()
        self.sensors[sid] = {"id": sid, "kind": kind, "name": name, "lat": lat, "lon": lon, "latest": latest, "updated_at": now}
        self.series[sid] = deque([{"t": now, **latest}], maxlen=300)

    def sensors_payload(self) -> list[dict]:
        return list(self.sensors.values())

    def tick(self):
        now = datetime.now(timezone.utc)
        hour = now.hour + now.minute / 60
        peak = math.exp(-((hour - 9.5) ** 2) / 4) + math.exp(-((hour - 18.5) ** 2) / 5)
        for s in self.sensors.values():
            v = s["latest"]
            if s["kind"] == "traffic":
                v["vehicles_per_min"] = max(5, int(v["vehicles_per_min"] + random.gauss(0, 4) + peak * 2 - 1))
                v["avg_speed_kmh"] = max(5, min(55, round(v["avg_speed_kmh"] + random.gauss(0, 2) - peak, 1)))
            elif s["kind"] == "air_quality":
                v["aqi"] = max(20, min(400, int(v["aqi"] + random.gauss(0, 6))))
                v["pm25"] = max(5, min(300, int(v["pm25"] + random.gauss(0, 4))))
                v["co_ppm"] = round(max(0.1, v["co_ppm"] + random.gauss(0, 0.05)), 2)
            elif s["kind"] == "road":
                v["water_level_cm"] = max(0, min(60, v["water_level_cm"] + random.choice([0, 0, 0, 1, -1])))
                v["temperature_c"] = round(v["temperature_c"] + random.gauss(0, 0.2), 1)
            elif s["kind"] == "emergency":
                v["calls_per_10min"] = max(0, int(v["calls_per_10min"] + random.choice([-1, 0, 0, 1])))
            else:
                v["er_occupancy_pct"] = round(max(10, min(100, v["er_occupancy_pct"] + random.gauss(0, 1))), 1)
                v["waiting_patients"] = max(0, v["waiting_patients"] + random.choice([-1, 0, 0, 1]))
            s["updated_at"] = now.isoformat()
            self.series[s["id"]].append({"t": s["updated_at"], **v})
        bus.publish("sensor_update", {"sensors": self.sensors_payload()})

    def drift_traffic(self):
        """Gentle random walk of traffic factors on roads without a manual incident flag."""
        with SessionLocal() as db:
            changed = []
            for t in db.scalars(select(m.Traffic)):
                if t.accident or t.blocked or random.random() > 0.25:
                    continue
                t.traffic_factor = round(max(1.0, min(2.4, t.traffic_factor + random.gauss(0, 0.08))), 3)
                t.traffic_level = graph_service.level_for_factor(t.traffic_factor)
                changed.append(t.road_id)
            db.commit()
            if changed:
                graph_service.invalidate()
                g = graph_service.get_graph(db)
                bus.publish("traffic_update", {"edges": [{"edge_id": e.id, "traffic_level": e.traffic_level,
                                                          "traffic_factor": e.traffic_factor, "blocked": e.blocked,
                                                          "accident": e.accident, "signal_priority": e.signal_priority}
                                                         for e in g.edges.values() if not e.id.startswith("ACC_")]})

    async def run(self):
        n = 0
        while True:
            await asyncio.sleep(BASE_INTERVAL_S / max(1, self.speed))
            try:
                self.tick()
                n += 1
                if n % 6 == 0:
                    await asyncio.to_thread(self.drift_traffic)
            except Exception:  # pragma: no cover - keep the loop alive
                log.exception("IoT tick failed")

    def start(self):
        self._task = asyncio.get_running_loop().create_task(self.run())

    def stop(self):
        if self._task:
            self._task.cancel()


iot = IoTSimulator()
