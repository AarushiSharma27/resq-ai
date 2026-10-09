"""RESQ-AI FastAPI application: REST API under /api, WebSockets under /ws."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import core, ops, platform
from app.config import get_settings
from app.database import SessionLocal
from app.database.session import Base, engine
from app.ml.service import MLError
from app.security import user_from_token
from app.seed import seed
from app.services.bus import bus
from app.services.incidents import DomainError
from app.services.iot import iot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("resq")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.models  # noqa: F401  (register tables)
    Base.metadata.create_all(engine)
    s = get_settings()
    if s.seed_demo_data:
        with SessionLocal() as db:
            seed(db)
    await bus.start()
    if s.iot_enabled:
        iot.start()
    log.info("RESQ-AI ready (%s mode)", s.data_mode)
    yield
    iot.stop()
    await bus.stop()


settings = get_settings()
app = FastAPI(title="RESQ-AI Emergency Response API", version=settings.version, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(DomainError)
async def domain_error(_req: Request, e: DomainError):
    return JSONResponse(status_code=e.status, content={"detail": {"code": e.code, "message": e.message, **e.extra}})


@app.exception_handler(MLError)
async def ml_error(_req: Request, e: MLError):
    return JSONResponse(status_code=e.status, content={"detail": {"code": e.code, "message": e.message}})


@app.exception_handler(HTTPException)
async def http_error(_req: Request, e: HTTPException):
    detail = e.detail if isinstance(e.detail, dict) else {"code": f"HTTP_{e.status_code}", "message": str(e.detail)}
    return JSONResponse(status_code=e.status_code, content={"detail": detail}, headers=getattr(e, "headers", None))


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    resp.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
    return resp


for r in (core.router, ops.router, platform.router):
    app.include_router(r)


async def _stream(ws: WebSocket, incident_id: str | None):
    token = ws.query_params.get("token", "")
    try:
        with SessionLocal() as db:
            user_from_token(db, token)
    except HTTPException:
        await ws.close(code=4401)
        return
    await ws.accept()
    q = bus.subscribe(incident_id)

    async def pump():
        while True:
            await ws.send_json(await q.get())

    sender = asyncio.create_task(pump())
    try:
        while True:
            await ws.receive_text()  # keep-alive / ignore client messages
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        bus.unsubscribe(q)


@app.websocket("/ws/global")
async def ws_global(ws: WebSocket):
    await _stream(ws, None)


@app.websocket("/ws/incidents/{incident_id}")
async def ws_incident(ws: WebSocket, incident_id: str):
    await _stream(ws, incident_id)
