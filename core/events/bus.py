"""
Crypto Bot v4.5 — Event Bus

Pub/sub event system powering the service-to-service communication.
Supports:
  - Memory bus (development / single-process)
  - Redis Streams (production / multi-process / multi-container)

Usage:
    from core.events.bus import event_bus

    # Publish
    event_bus.publish("signal.generated", {"pair": "BTCUSDT", ...})

    # Subscribe
    @event_bus.subscribe("signal.generated")
    async def handle_signal(event: dict):
        ...
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Union
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# Event Data
# ═══════════════════════════════════════════════════════════════

@dataclass
class BusEvent:
    """Event propagated through the bus."""
    topic: str
    data: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid4().hex[:12])
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = ""


# ═══════════════════════════════════════════════════════════════
# Memory Bus (single-process)
# ═══════════════════════════════════════════════════════════════

class MemoryBus:
    """In-process pub/sub bus for development and testing."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._history: List[BusEvent] = []
        self._max_history = 1000

    def publish(self, topic: str, data: dict, source: str = "") -> BusEvent:
        """Publish an event to all subscribers of `topic`."""
        event = BusEvent(topic=topic, data=data, source=source)

        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Notify specific topic
        callbacks = self._subscribers.get(topic, [])
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                logger.warning("event_callback_failed", topic=topic, exc_info=True)

        # Notify wildcard subscribers
        for cb in self._subscribers.get("*", []):
            try:
                cb(event)
            except Exception:
                logger.warning("event_wildcard_callback_failed", topic=topic, exc_info=True)

        return event

    def subscribe(self, topic: str, callback: Callable):
        """Subscribe to a topic."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(callback)

    async def replay(self, topic: Optional[str] = None, limit: int = 100) -> List[BusEvent]:
        """Replay recent events (used by new services to catch up)."""
        events = self._history
        if topic:
            events = [e for e in events if e.topic == topic]
        return events[-limit:]


# ═══════════════════════════════════════════════════════════════
# Redis Streams Bus (multi-process / production)
# ═══════════════════════════════════════════════════════════════

class RedisStreamBus:
    """Redis Streams pub/sub for multi-process production deployments."""

    STREAM_PREFIX = "crypto_bot_v4:events:"
    CONSUMER_GROUP = "crypto_bot_v4"
    MAX_STREAM_LEN = 10000

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis = None
        self._memory_bus = MemoryBus()  # fallback
        self._running = False
        self._consumer_name = f"consumer_{uuid4().hex[:8]}"
        self._topics: Set[str] = set()

    def _ensure_redis(self):
        if self._redis is not None:
            return True
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url)
            return True
        except Exception as e:
            logger.warning("redis_unavailable_fallback", error=str(e))
            return False

    def publish(self, topic: str, data: dict, source: str = "") -> BusEvent:
        """Publish to Redis Stream + memory fallback."""
        event = BusEvent(topic=topic, data=data, source=source)

        if self._ensure_redis():
            try:
                payload = {"topic": topic, "data": json.dumps(data, default=str),
                          "source": source, "timestamp": event.timestamp}
                self._redis.xadd(
                    f"{self.STREAM_PREFIX}{topic}",
                    payload,
                    maxlen=self.MAX_STREAM_LEN,
                )
            except Exception:
                logger.warning("redis_publish_failed", topic=topic)

        # Always publish via memory bus as sync fallback
        self._memory_bus.publish(topic, data, source)
        return event

    def subscribe(self, topic: str, callback: Callable):
        """Subscribe via memory bus (Redis streams are polled in background)."""
        self._topics.add(topic)
        self._memory_bus.subscribe(topic, callback)

    async def start_consumer(self):
        """Start background Redis Stream consumer."""
        if not self._ensure_redis():
            return

        self._running = True
        logger.info("redis_stream_consumer_started", consumer=self._consumer_name)

        for topic in self._topics:
            stream = f"{self.STREAM_PREFIX}{topic}"
            try:
                await self._redis.xgroup_create(stream, self.CONSUMER_GROUP, "0", mkstream=True)
            except Exception:
                pass  # group already exists

        while self._running:
            try:
                streams = {f"{self.STREAM_PREFIX}{t}": ">" for t in self._topics}
                if not streams:
                    await asyncio.sleep(1)
                    continue

                results = await self._redis.xreadgroup(
                    self.CONSUMER_GROUP, self._consumer_name,
                    streams, count=10, block=1000,
                )

                for stream, messages in results:
                    for msg_id, payload in messages:
                        topic = payload.get(b"topic", b"").decode()
                        data = json.loads(payload.get(b"data", b"{}").decode())
                        self._memory_bus.publish(topic, data)

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(2)

    async def stop_consumer(self):
        self._running = False


# ═══════════════════════════════════════════════════════════════
# Hybrid EventBus (auto-selects backend)
# ═══════════════════════════════════════════════════════════════

class EventBus:
    """
    Hybrid event bus: MemoryBus for dev, RedisStreamBus for prod.
    Auto-detects Redis availability.
    """

    # Standard topics for type-safe publishing
    class Topics:
        SIGNAL_GENERATED = "signal.generated"
        SIGNAL_APPROVED = "signal.approved"
        SIGNAL_REJECTED = "signal.rejected"
        ORDER_PLACED = "order.placed"
        ORDER_FILLED = "order.filled"
        ORDER_FAILED = "order.failed"
        POSITION_OPENED = "position.opened"
        POSITION_CLOSED = "position.closed"
        STOP_MOVED = "position.stop_moved"
        REGIME_CHANGED = "regime.changed"
        CONFIG_UPDATED = "config.updated"
        RECOVERY_ENTERED = "recovery.entered"
        RECOVERY_EXITED = "recovery.exited"
        HEALTH_CHANGED = "health.changed"
        TV_ALERT_RECEIVED = "tradingview.alert_received"
        TV_SIGNAL_CREATED = "tradingview.signal_created"

    def __init__(self, redis_url: Optional[str] = None):
        self._redis = RedisStreamBus(redis_url) if redis_url or os.getenv("REDIS_URL") else None
        self._memory = MemoryBus()

    def publish(self, topic: str, data: dict, source: str = "") -> BusEvent:
        event = BusEvent(topic=topic, data=data, source=source)
        self._memory.publish(topic, data, source)
        if self._redis:
            self._redis.publish(topic, data, source)
        return event

    def subscribe(self, topic: str, callback: Callable):
        self._memory.subscribe(topic, callback)
        if self._redis:
            self._redis.subscribe(topic, callback)

    async def start(self):
        if self._redis:
            await self._redis.start_consumer()

    async def stop(self):
        if self._redis:
            await self._redis.stop_consumer()

    def replay(self, topic: Optional[str] = None, limit: int = 100):
        return self._memory.replay(topic, limit)


# Global singleton
event_bus = EventBus()
