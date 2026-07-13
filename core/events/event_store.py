"""
Crypto Bot v4.4 — Event Store
Event sourcing implementation for Portfolio Engine.
"""

from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    TRADE_OPENED = "trade_opened"
    TRADE_FILLED = "trade_filled"
    POSITION_CREATED = "position_created"
    STOP_MOVED = "stop_moved"
    POSITION_CLOSED = "position_closed"
    CONFIG_UPDATED = "config_updated"
    RECOVERY_ENTERED = "recovery_entered"
    RECOVERY_EXITED = "recovery_exited"
    HEALTH_CHANGED = "health_changed"


@dataclass
class Event:
    """Event sourcing event."""
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    type: EventType = EventType.TRADE_OPENED
    data: dict = field(default_factory=dict)
    sequence: int = 0

    def to_dict(self) -> dict:
        return {
            "event_id": str(self.event_id),
            "timestamp": self.timestamp.isoformat(),
            "type": self.type.value,
            "data": self.data,
            "sequence": self.sequence,
        }


class EventStore:
    """
    Append-only event store for Portfolio state reconstruction.
    Supports replay to rebuild current state from history.
    """

    def __init__(self):
        self._events: List[Event] = []
        self._sequence: int = 0
        self._subscribers: dict = {}

    def append(self, event_type: EventType, data: dict) -> Event:
        """Append a new event to the store."""
        self._sequence += 1
        event = Event(
            timestamp=datetime.utcnow(),
            type=event_type,
            data=data,
            sequence=self._sequence,
        )
        self._events.append(event)
        self._notify(event)
        return event

    def _notify(self, event: Event):
        """Notify subscribers of a new event."""
        for callback in self._subscribers.get(event.type, []):
            try:
                callback(event)
            except Exception as e:
                # Log but don't crash — subscriber failures shouldn't halt trading
                pass

    def subscribe(self, event_type: EventType, callback):
        """Subscribe to events of a given type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def replay(self, until_sequence: Optional[int] = None) -> List[Event]:
        """Replay events to reconstruct state."""
        if until_sequence is None:
            return list(self._events)
        return [e for e in self._events if e.sequence <= until_sequence]

    def get_events_by_type(self, event_type: EventType) -> List[Event]:
        """Filter events by type."""
        return [e for e in self._events if e.type == event_type]

    def get_events_since(self, timestamp: datetime) -> List[Event]:
        """Get events after a given timestamp."""
        return [e for e in self._events if e.timestamp >= timestamp]

    @property
    def count(self) -> int:
        return len(self._events)

    def clear(self):
        """Clear all events (use with caution)."""
        self._events.clear()
        self._sequence = 0


# Global singleton
event_store = EventStore()
