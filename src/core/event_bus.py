"""
Event Bus —— 基于 blinker（Flask/Werkzeug 生态信号系统）

替换了原有的手写 260 行 EventBus 实现。
blinker 提供线程安全、高性能的发布/订阅机制。

用法：
  from core.event_bus import emit, on

  emit("memory.written", {"alpha_id": "Ghost-001", "content": "..."})

  @on("memory.written")
  def on_memory(event):
      print(event.data)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from blinker import Namespace

logger = logging.getLogger(__name__)

_namespace = Namespace()


class EventType:
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_REPLIED = "message.replied"
    MEMORY_WRITTEN = "memory.written"
    MEMORY_RECALLED = "memory.recalled"
    TOOL_CALLED = "tool.called"
    TOOL_RESULT = "tool.result"
    AGENT_THOUGHT = "agent.thought"
    SOCIAL_FRIEND_REQUEST = "social.friend_request"
    SOCIAL_MESSAGE = "social.message"
    A2A_CALL = "a2a.call"
    A2A_RESPONSE = "a2a.response"
    SYSTEM_ERROR = "system.error"
    SYSTEM_HEALTH = "system.health"


@dataclass
class Event:
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
        }


class EventBus:
    def __init__(self, max_history: int = 1000):
        self._signals: Dict[str, Any] = {}
        self._wrappers: Dict[str, List[Callable]] = {}
        self._history: List[Event] = []
        self._max_history = max_history
        self._stats = {"emitted": 0, "dispatched": 0}

    def _get_signal(self, event_type: str):
        if event_type not in self._signals:
            self._signals[event_type] = _namespace.signal(event_type)
        return self._signals[event_type]

    def on(self, event_type: str, callback: Callable = None, subscriber_id: str = None):
        def _wrap(func: Callable) -> Callable:
            def wrapper(sender, **kwargs):
                event = kwargs.get("bus_event")
                if event is not None:
                    func(event.data if isinstance(event, Event) else event)
                else:
                    func(kwargs)
            self._wrappers.setdefault(event_type, []).append(wrapper)
            return wrapper

        def decorator(func: Callable) -> Callable:
            self._get_signal(event_type).connect(_wrap(func))
            return func

        if callback is not None:
            self._get_signal(event_type).connect(_wrap(callback))
            return None
        return decorator

    def once(self, event_type: str, callback: Callable, subscriber_id: str = None):
        def wrapper(sender, **kwargs):
            try:
                event = kwargs.get("bus_event")
                if event is not None:
                    callback(event.data if isinstance(event, Event) else event)
                else:
                    callback(kwargs)
            finally:
                self._get_signal(event_type).disconnect(wrapper)
                if event_type in self._wrappers:
                    self._wrappers[event_type] = [
                        w for w in self._wrappers[event_type] if w is not wrapper
                    ]

        self._wrappers.setdefault(event_type, []).append(wrapper)
        self._get_signal(event_type).connect(wrapper)

    def off(self, event_type: str, callback: Callable = None, subscriber_id: str = None):
        if event_type in self._signals:
            signal = self._signals[event_type]
            if callback:
                signal.disconnect(callback)
            else:
                signal.receivers.clear()
        if event_type in self._wrappers:
            self._wrappers.pop(event_type, None)

    def emit(self, event_type: str, data: Dict[str, Any] = None, source: str = "") -> Event:
        event = Event(event_type=event_type, data=data or {}, source=source)
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        self._stats["emitted"] += 1

        try:
            signal = self._get_signal(event_type)
            signal.send(self, bus_event=event, **(data or {}))
            self._stats["dispatched"] += 1
        except Exception as e:
            logger.error("事件分发异常 [%s]: %s", event_type, e)

        return event

    def get_history(self, event_type: str = None, limit: int = 100) -> List[Event]:
        events = self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "event_types": list(self._signals.keys()),
        }

    def clear(self):
        self._signals.clear()
        self._wrappers.clear()
        self._history.clear()
        self._stats = {"emitted": 0, "dispatched": 0}

    def subscribe_count(self, event_type: str) -> int:
        if event_type not in self._signals:
            return 0
        return len(list(self._signals[event_type].receivers))


_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def emit(event_type: str, data: Dict[str, Any] = None, source: str = "") -> Event:
    return get_event_bus().emit(event_type, data, source)


def on(event_type: str, callback: Callable = None, subscriber_id: str = None):
    return get_event_bus().on(event_type, callback, subscriber_id)