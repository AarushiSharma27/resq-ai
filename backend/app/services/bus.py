"""Real-time event bus → WebSocket fan-out.

Messages published anywhere (sync request threads, background tasks) are delivered to
connected WebSocket clients. When REDIS_URL is configured the bus goes through a Redis
pub/sub channel so several backend workers share one stream; otherwise it fans out
in-process.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.config import get_settings

log = logging.getLogger("resq.bus")
CHANNEL = "resq:events"


class EventBus:
    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.subscribers: dict[asyncio.Queue, str | None] = {}  # queue -> incident filter
        self.redis = None
        self._relay_task: asyncio.Task | None = None

    async def start(self):
        self.loop = asyncio.get_running_loop()
        url = get_settings().redis_url
        if url:
            try:
                import redis.asyncio as aioredis
                self.redis = aioredis.from_url(url)
                await self.redis.ping()
                self._relay_task = asyncio.create_task(self._relay())
                log.info("Event bus using Redis pub/sub at %s", url)
            except Exception as e:  # pragma: no cover - depends on infra
                log.warning("Redis unavailable (%s) - falling back to in-process bus", e)
                self.redis = None

    async def stop(self):
        if self._relay_task:
            self._relay_task.cancel()
        if self.redis:
            await self.redis.aclose()

    async def _relay(self):  # pragma: no cover - needs redis
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        async for msg in pubsub.listen():
            if msg.get("type") == "message":
                self._fanout(json.loads(msg["data"]))

    def subscribe(self, incident_id: str | None = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.subscribers[q] = incident_id
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self.subscribers.pop(q, None)

    def _fanout(self, msg: dict):
        for q, flt in list(self.subscribers.items()):
            if flt is None or msg.get("incident_id") == flt:
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:
                    pass  # slow consumer: drop oldest-style behaviour (skip)

    def publish(self, type_: str, data: dict, incident_id: str | None = None):
        msg = {"type": type_, "incident_id": incident_id, "ts": datetime.now(timezone.utc).isoformat(), "data": data}
        if self.loop is None:
            return  # app not started (e.g. unit tests without lifespan)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if self.redis is not None:
            coro = self.redis.publish(CHANNEL, json.dumps(msg, default=str))
            if running is self.loop:
                asyncio.ensure_future(coro)
            else:
                asyncio.run_coroutine_threadsafe(coro, self.loop)
            return
        if running is self.loop:
            self._fanout(msg)
        else:
            self.loop.call_soon_threadsafe(self._fanout, msg)


bus = EventBus()
