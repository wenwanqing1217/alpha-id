# TERM: EventBus — Redis Streams 跨服务事件总线（替代旧 blinker 实现）
# TERM: EventType — 事件类型常量枚举
# TERM: Event — 事件数据结构（event_id, event_type, data, timestamp, source）

"""
Event Bus — 基于 Redis Streams（跨服务）+ 本地处理器（进程内）

替换了原有的 blinker 实现。接口完全不变，底层改用 Redis Streams：
  - emit() → XADD 到 Redis Stream + 调用本地处理器
  - on()  → 注册本地处理器
  - start_consuming() → XREADGROUP 循环，消费跨服务事件并分发给本地处理器

用法（完全兼容旧代码）：
  from core.event_bus import emit, on, get_event_bus

  emit("memory.written", {"alpha_id": "Ghost-001", "content": "..."})

  @on("memory.written")
  def on_memory(event):
      print(event.data)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import redis

from core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# ── Redis Streams 配置 ──

STREAM_PREFIX = os.getenv("EVENT_STREAM_PREFIX", "alphaid:events")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# ── 常量 ──

_MAX_HISTORY = 1000
_BLOCK_TIMEOUT_MS = 5000
_BATCH_SIZE = 10


# TERM: EventBus — Redis Streams 跨服务事件总线（替代旧 blinker 实现）


class EventType:
    """事件类型常量"""
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
    GROWTH_EVENT = "growth.event"  # 成长事件：任务成功执行 → 累计成长值


@dataclass
class Event:
    """事件数据结构"""
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
    """
    事件总线 — Redis Streams 跨服务 + 本地处理器

    架构：
      emit() → XADD (Redis Stream) + 本地处理器
      start_consuming() → XREADGROUP 循环 → 本地处理器
      on() → 注册本地处理器
    """

    def __init__(self, max_history: int = _MAX_HISTORY):
        self._local_handlers: Dict[str, List[Callable]] = {}
        self._once_handlers: Dict[str, List[Callable]] = {}
        self._history: List[Event] = []
        self._max_history = max_history
        self._stats = {"emitted": 0, "dispatched_local": 0, "dispatched_remote": 0}
        self._consuming = False
        self._consumer_thread: Optional[threading.Thread] = None
        self._consumer_name = f"consumer-{uuid.uuid4().hex[:8]}"
        self._consumer_group = "alphaid-processors"
        self._lock = threading.Lock()

    # ── 本地处理器注册 ──

    def on(self, event_type: str, callback: Callable = None, subscriber_id: str = None):
        """注册事件处理器（兼容 blinker 接口）"""
        def _wrap(func: Callable) -> Callable:
            def wrapper(event_data):
                if isinstance(event_data, Event):
                    func(event_data.data)
                elif isinstance(event_data, dict):
                    func(event_data)
                else:
                    func({"data": event_data})
            self._local_handlers.setdefault(event_type, []).append(wrapper)
            return wrapper

        if callback is not None:
            _wrap(callback)
            return None
        return _wrap

    def once(self, event_type: str, callback: Callable, subscriber_id: str = None):
        """注册一次性处理器"""
        def wrapper(event_data):
            try:
                if isinstance(event_data, Event):
                    callback(event_data.data)
                elif isinstance(event_data, dict):
                    callback(event_data)
                else:
                    callback({"data": event_data})
            finally:
                # 自动移除
                if event_type in self._local_handlers:
                    self._local_handlers[event_type] = [
                        h for h in self._local_handlers[event_type] if h is not wrapper
                    ]
        self._local_handlers.setdefault(event_type, []).append(wrapper)

    def off(self, event_type: str, callback: Callable = None, subscriber_id: str = None):
        """注销事件处理器"""
        if callback:
            if event_type in self._local_handlers:
                self._local_handlers[event_type] = [
                    h for h in self._local_handlers[event_type]
                    if (h.__wrapped__ if hasattr(h, '__wrapped__') else h) != callback
                ]
        else:
            self._local_handlers.pop(event_type, None)

    # ── 事件发布 ──

    def emit(self, event_type: str, data: Dict[str, Any] = None, source: str = "") -> Event:
        """
        发布事件 — 写入 Redis Streams + 调用本地处理器

        这是唯一的 emit 入口，保证事件不丢失：
        1. 构造 Event 对象
        2. 追加到本地历史
        3. 调用本地处理器（同步，同 blinker 行为）
        4. 写入 Redis Streams（跨服务通信）
        """
        event = Event(event_type=event_type, data=data or {}, source=source)
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        self._stats["emitted"] += 1

        # 1. 调用本地处理器（同步，保持 blinker 的即时性）
        self._dispatch_local(event)
        self._stats["dispatched_local"] += 1

        # 2. 写入 Redis Streams（跨服务通信）
        try:
            redis_client = get_redis_client()
            stream_key = f"{STREAM_PREFIX}:{event_type}"
            payload = {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "data": json.dumps(event.data),
                "source": event.source,
                "timestamp": str(event.timestamp),
            }
            redis_client.xadd(stream_key, payload, maxlen=10000, approximate=True)
        except Exception as e:
            logger.error("EventBus emit to Redis failed [%s]: %s", event_type, e)

        return event

    def _dispatch_local(self, event: Event):
        """分发给本地处理器（同步）"""
        handlers = self._local_handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error("本地处理器异常 [%s]: %s", event.event_type, e)

    # ── 跨服务消费 ──

    def start_consuming(self):
        """
        启动 Redis Streams 消费者（后台线程）

        消费流程：
        1. 为所有已注册事件类型创建 consumer group
        2. 后台线程运行 XREADGROUP 循环
        3. 收到事件 → 分发给本地处理器
        """
        if self._consuming:
            logger.warning("EventBus 已在消费中")
            return

        self._consuming = True
        self._consumer_thread = threading.Thread(
            target=self._consume_loop,
            name="eventbus-consumer",
            daemon=True,
        )
        self._consumer_thread.start()
        logger.info(
            "EventBus 消费启动: consumer=%s, group=%s",
            self._consumer_name,
            self._consumer_group,
        )

    def stop_consuming(self):
        """停止消费"""
        self._consuming = False
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=5)
        logger.info("EventBus 消费停止")

    def _consume_loop(self):
        """XREADGROUP 消费循环（后台线程）"""
        redis_client = get_redis_client()

        # 为所有已注册事件类型创建 consumer group
        stream_keys = []
        for event_type in self._local_handlers.keys():
            stream_key = f"{STREAM_PREFIX}:{event_type}"
            stream_keys.append(stream_key)
            try:
                redis_client.xgroup_create(stream_key, self._consumer_group, id="0", mkstream=True)
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    logger.warning("创建 consumer group 失败 [%s]: %s", stream_key, e)

        if not stream_keys:
            logger.info("EventBus 无注册处理器，消费循环等待中...")
            # 即使没有初始处理器，也保持循环运行（后续注册的处理器也能收到）
            stream_keys = [f"{STREAM_PREFIX}:{et}" for et in EventType.__dict__.values() if isinstance(et, str)]
            for stream_key in stream_keys:
                try:
                    redis_client.xgroup_create(stream_key, self._consumer_group, id="0", mkstream=True)
                except redis.exceptions.ResponseError as e:
                    if "BUSYGROUP" not in str(e):
                        logger.debug("EventBus 自动创建 consumer group [%s]: %s", stream_key, e)

        logger.info("EventBus 消费循环启动: %d 个 stream", len(stream_keys))

        # Build streams dict: {stream_key: ">"} — ">" means only new messages
        streams_dict = {sk: ">" for sk in stream_keys}

        while self._consuming:
            try:
                result = redis_client.xreadgroup(
                    groupname=self._consumer_group,
                    consumername=self._consumer_name,
                    streams=streams_dict,
                    count=_BATCH_SIZE,
                    block=_BLOCK_TIMEOUT_MS,
                )

                if not result:
                    continue

                for stream_key, messages in result:
                    event_type = stream_key.replace(f"{STREAM_PREFIX}:", "")
                    for message_id, fields in messages:
                        self._process_remote_event(event_type, message_id, fields)

            except redis.exceptions.TimeoutError:
                # XREADGROUP 阻塞读的空闲超时（无新消息）是正常现象，静默继续等待
                continue
            except Exception as e:
                logger.error("EventBus 消费循环异常: %s", e)
                time.sleep(1)

    def _process_remote_event(self, event_type: str, message_id: str, fields: Dict[str, str]):
        """处理来自 Redis Streams 的远程事件"""
        try:
            event_data = {}
            if "data" in fields:
                try:
                    event_data = json.loads(fields["data"])
                except (json.JSONDecodeError, TypeError):
                    event_data = {"raw": fields.get("data", "")}

            event = Event(
                event_type=event_type,
                data=event_data,
                event_id=fields.get("event_id", ""),
                timestamp=float(fields.get("timestamp", time.time())),
                source=fields.get("source", "remote"),
            )

            # 分发给本地处理器
            self._dispatch_local(event)
            self._stats["dispatched_remote"] += 1

            # ACK
            try:
                redis_client = get_redis_client()
                redis_client.xack(f"{STREAM_PREFIX}:{event_type}", self._consumer_group, message_id)
            except Exception as e:
                logger.error("EventBus ACK 失败 [%s:%s]: %s", event_type, message_id, e)

        except Exception as e:
            logger.error("EventBus 处理远程事件失败 [%s:%s]: %s", event_type, message_id, e)

    # ── 查询 ──

    def get_history(self, event_type: str = None, limit: int = 100) -> List[Event]:
        events = self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "event_types": list(self._local_handlers.keys()),
            "consuming": self._consuming,
            "consumer_name": self._consumer_name,
        }

    def clear(self):
        with self._lock:
            self._local_handlers.clear()
            self._history.clear()
            self._stats = {"emitted": 0, "dispatched_local": 0, "dispatched_remote": 0}

    def subscribe_count(self, event_type: str) -> int:
        return len(self._local_handlers.get(event_type, []))


# ── 全局单例 ──

_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局 EventBus 实例（单例）"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def emit(event_type: str, data: Dict[str, Any] = None, source: str = "") -> Event:
    """便捷函数：发布事件"""
    return get_event_bus().emit(event_type, data, source)


def on(event_type: str, callback: Callable = None, subscriber_id: str = None):
    """便捷函数：注册处理器"""
    return get_event_bus().on(event_type, callback, subscriber_id)
