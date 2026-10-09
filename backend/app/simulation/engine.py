"""Discrete-time response simulation.

Each tick advances simulated time by TICK_REAL_S * speed * TIME_COMPRESSION seconds. Units
drive along their A* route to the scene, ambulances then transport patients to the
allocated hospital, other units return to base, and the incident is resolved. Vehicle
positions, timeline events and status changes are pushed over the event bus.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.database import SessionLocal
from app.services import graph_service, incidents, resources
from app.services import serializers as ser
from app.services.bus import bus
from app.services.events import log_event
from app.utils.geo import point_along, polyline_length_m

log = logging.getLogger("resq.sim")
TICK_REAL_S = 0.5
TIME_COMPRESSION = 6.0  # at 1x one real second = 6 simulated seconds
ON_SCENE_S = 240.0


class Run:
    def __init__(self, run_id: str, incident_id: str, speed: float):
        self.run_id, self.incident_id, self.speed = run_id, incident_id, float(speed)
        self.t = 0.0
        self.status = "RUNNING"
        self.timeline: list[dict] = []
        self.vehicles: dict[int, dict] = {}
        self.metrics: dict | None = None
        self.task: asyncio.Task | None = None


class SimulationManager:
    def __init__(self):
        self.runs: dict[str, Run] = {}

    def _next_id(self, db: Session) -> str:
        n = len(db.scalars(select(m.SimulationRun.id)).all()) + 1
        return f"SIM-{datetime.now(timezone.utc):%Y%m%d}-{n:04d}"

    def start(self, db: Session, incident_id: str, speed: float = 1) -> str:
        run_id = self._next_id(db)
        db.add(m.SimulationRun(id=run_id, incident_id=incident_id, speed=speed, config={"speed": speed}))
        db.commit()
        run = Run(run_id, incident_id, speed)
        self.runs[run_id] = run
        if bus.loop is None:
            run.status = "FAILED"
            return run_id
        bus.loop.call_soon_threadsafe(lambda: setattr(run, "task", bus.loop.create_task(self._drive(run))))
        return run_id

    def set_speed(self, run_id: str, speed: float) -> None:
        if run_id in self.runs:
            self.runs[run_id].speed = float(speed)

    def snapshot(self, db: Session, run_id: str) -> dict | None:
        row = db.get(m.SimulationRun, run_id)
        if row is None:
            return None
        live = self.runs.get(run_id)
        timeline = live.timeline if live else [{"t_s": e.t_s, "label": e.label, "type": e.type} for e in row.events]
        return {"run_id": row.id, "incident_id": row.incident_id, "status": live.status if live else row.status,
                "speed": live.speed if live else row.speed, "started_at": ser.iso(row.started_at),
                "finished_at": ser.iso(row.finished_at), "sim_time_s": round(live.t if live else row.sim_time_s, 1),
                "timeline": timeline, "vehicles": list(live.vehicles.values()) if live else [],
                "metrics": live.metrics if live else row.metrics}

    # ------------------------------------------------------------------ driver
    def _event(self, db: Session, run: Run, label: str, type_: str):
        ev = {"t_s": round(run.t, 1), "label": label, "type": type_}
        run.timeline.append(ev)
        db.add(m.SimulationEvent(run_id=run.run_id, t_s=ev["t_s"], type=type_, label=label))
        db.commit()
        bus.publish("simulation_event", {"run_id": run.run_id, **ev}, run.incident_id)

    async def _drive(self, run: Run):
        try:
            await self._simulate(run)
        except Exception as e:  # pragma: no cover - surfaced to clients as FAILED
            log.exception("simulation %s failed", run.run_id)
            run.status = "FAILED"
            with SessionLocal() as db:
                row = db.get(m.SimulationRun, run.run_id)
                row.status = "FAILED"
                db.commit()
            bus.publish("simulation_status", {"run_id": run.run_id, "status": "FAILED", "error": str(e)}, run.incident_id)

    async def _simulate(self, run: Run):
        with SessionLocal() as db:
            inc = db.get(m.Incident, run.incident_id)
            g = graph_service.get_graph(db)
            units = list(db.scalars(select(m.Resource).where(m.Resource.assigned_incident_id == inc.id)))
            hosp = db.get(m.Hospital, inc.hospital_id) if inc.hospital_id else None
            legs: dict[int, dict] = {}
            for u in units:
                plat, plon = resources.position(u)
                r = g.route_points((plat, plon), (inc.lat, inc.lon), "astar")
                geom = r["geometry"] if r["found"] else [[plat, plon], [inc.lat, inc.lon]]
                dur = max(30.0, r["travel_time_s"] or 300.0)
                legs[u.id] = {"phase": "TO_SCENE", "geom": geom, "start": 0.0, "dur": dur, "dest": inc.location_name}
                u.status = "EN_ROUTE"
            db.commit()
            self._event(db, run, f"{len(units)} units dispatched to {inc.location_name or inc.title}", "DISPATCH")
            first_arrival = None
            transport_done = None
            on_scene_count = 0

            while True:
                await asyncio.sleep(TICK_REAL_S)
                run.t += TICK_REAL_S * run.speed * TIME_COMPRESSION
                for u in units:
                    leg = legs[u.id]
                    frac = min(1.0, (run.t - leg["start"]) / leg["dur"])
                    if leg["phase"] in ("TO_SCENE", "TRANSPORT", "RETURN"):
                        lat, lon, heading = point_along(leg["geom"], frac)
                        if u.location:
                            u.location.lat, u.location.lon, u.location.heading = lat, lon, heading
                        u.eta_s = round(max(0.0, leg["dur"] - (run.t - leg["start"])), 1)
                        leg.setdefault("kmh", round(polyline_length_m(leg["geom"]) / leg["dur"] * 3.6, 1))
                        u.speed_kmh = 0.0 if frac >= 1 else leg["kmh"]
                    if frac < 1:
                        continue
                    if leg["phase"] == "TO_SCENE":
                        leg.update(phase="ON_SCENE", start=run.t, dur=ON_SCENE_S)
                        u.status = "ON_SCENE"
                        on_scene_count += 1
                        self._event(db, run, f"{u.code} arrived on scene", "ARRIVAL")
                        if first_arrival is None:
                            first_arrival = run.t
                            inc.response_time_s = round(run.t, 1)
                            if inc.state == "HOSPITAL_ALLOCATION":
                                incidents.transition(db, inc, "ACTIVE_RESPONSE", f"{u.code} on scene")
                    elif leg["phase"] == "ON_SCENE":
                        if u.kind == "AMBULANCE" and hosp is not None:
                            r = g.route_points((inc.lat, inc.lon), (hosp.lat, hosp.lon), "astar", dst_kinds=("hospital",))
                            leg.update(phase="TRANSPORT", start=run.t, dur=max(30.0, r["travel_time_s"] or 300.0),
                                       geom=r["geometry"] if r["found"] else [[inc.lat, inc.lon], [hosp.lat, hosp.lon]],
                                       dest=hosp.name)
                            u.status, u.destination = "TRANSPORTING", hosp.name
                            self._event(db, run, f"{u.code} transporting patients to {hosp.name}", "TRANSPORT")
                        else:
                            leg.update(phase="RETURN", start=run.t, dur=180.0,
                                       geom=[[inc.lat, inc.lon], [u.home_lat, u.home_lon]], dest=u.station)
                            u.status, u.destination = "RETURNING", u.station
                    elif leg["phase"] == "TRANSPORT":
                        leg.update(phase="DONE")
                        u.status = "AT_HOSPITAL"
                        if hosp is not None and hosp.capacity.emergency_beds_occupied < hosp.capacity.emergency_beds_total:
                            hosp.capacity.emergency_beds_occupied += 1
                        self._event(db, run, f"{u.code} delivered patients to {hosp.name}", "HOSPITAL")
                        transport_done = run.t
                    elif leg["phase"] == "RETURN":
                        leg.update(phase="DONE")
                db.commit()
                run.vehicles = {u.id: {"resource_id": u.id, "code": u.code, "kind": u.kind,
                                       "lat": u.location.lat if u.location else u.home_lat,
                                       "lon": u.location.lon if u.location else u.home_lon, "status": u.status,
                                       "speed_kmh": u.speed_kmh,
                                       "eta_s": u.eta_s, "destination": legs[u.id]["dest"], "incident_id": inc.id,
                                       "heading": u.location.heading if u.location else 0.0} for u in units}
                bus.publish("vehicle_positions", {"run_id": run.run_id, "vehicles": list(run.vehicles.values())}, inc.id)
                if all(legs[u.id]["phase"] == "DONE" for u in units) or run.t > 6 * 3600:
                    break

            run.metrics = {"response_time_s": round(first_arrival, 1) if first_arrival is not None else None,
                           "transport_time_s": round(transport_done - first_arrival, 1)
                           if transport_done and first_arrival is not None else None,
                           "total_time_s": round(run.t, 1), "units": len(units)}
            if inc.state == "ACTIVE_RESPONSE":
                incidents.transition(db, inc, "RESOLVED", "Simulation completed")
            resources.release(db, inc.id)
            run.status = "COMPLETED"
            self._event(db, run, "Incident resolved, units released", "RESOLVED")
            row = db.get(m.SimulationRun, run.run_id)
            row.status, row.metrics, row.sim_time_s = "COMPLETED", run.metrics, run.t
            row.finished_at = datetime.now(timezone.utc)
            db.commit()
            log_event(db, "SIMULATION_COMPLETED", f"{run.run_id} finished in {run.t / 60:.1f} sim-min", inc.id,
                      payload=run.metrics)
            bus.publish("simulation_status", {"run_id": run.run_id, "status": "COMPLETED", "metrics": run.metrics}, inc.id)
            bus.publish("hospital_update", {"hospitals": [ser.hospital(h) for h in db.scalars(select(m.Hospital))]}, None)


manager = SimulationManager()
