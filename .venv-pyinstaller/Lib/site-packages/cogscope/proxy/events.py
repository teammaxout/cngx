"""Thread-safe event bus for proxy → TUI communication."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class CaptureEvent:
    timestamp: datetime
    trace_id: str
    model: str
    task_id: str
    depth: int
    verification_steps: int
    hedging_ratio: float
    drift_score: Optional[float] = None
    baseline_name: Optional[str] = None
    alert: bool = False
    alert_message: Optional[str] = None
    metric_shifts: list[dict] = field(default_factory=list)
    no_baseline: bool = False
    session_id: Optional[str] = None
    session_turn: Optional[int] = None
    session_turn_count: Optional[int] = None
    session_health: Optional[str] = None
    session_stability_warning: bool = False
    session_warning_message: Optional[str] = None


class EventBus:
    def __init__(self, maxsize: int = 500):
        self._queue: queue.Queue[CaptureEvent] = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self._recent: list[CaptureEvent] = []
        self._max_recent = 50

    def publish(self, event: CaptureEvent) -> None:
        with self._lock:
            self._recent.append(event)
            if len(self._recent) > self._max_recent:
                self._recent = self._recent[-self._max_recent :]
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass

    def drain(self, timeout: float = 0.1) -> list[CaptureEvent]:
        events: list[CaptureEvent] = []
        try:
            while True:
                events.append(self._queue.get(timeout=timeout))
        except queue.Empty:
            pass
        return events

    def recent(self) -> list[CaptureEvent]:
        with self._lock:
            return list(self._recent)


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
