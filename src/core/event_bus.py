"""
Event Bus —— Ghost 平台事件总线

模块间通信全部走事件，不再直接调用。
订阅模式：模块只关心自己需要的事件。

事件类型：
  - message.received    : 收到用户消息
  - message.replied     : 已回复用户
  - memory.written      : 记忆已写入
  - memory.recalled     : 记忆被召回
  - tool.called         : 工具被调用
  - tool.result         : 工具返回结果
  - agent.thought       : Agent 思考过程
  - social.friend_request : 好友请求
  - social.message      : 社交消息
  - a2a.call            : A2A 调用
  - a2a.response        : A2A 响应
  - system.error        : 系统错误
  - system.health       : 健康检查

用法：
  # 发布
  event_bus.emit("memory.written", {"alpha_id": "Ghost-001", "content": "..."})

  # 订阅
  @event_bus.on("memory.written")
  def on_memory(event):
      print(event.data)
"""
import logging
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType:
    """事件类型常量"""
    # 消息
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_REPLIED = "message.replied"
    # 记忆
    MEMORY_WRITTEN = "memory.written"
    MEMORY_RECALLED = "memory.recalled"
    # 工具
    TOOL_CALLED = "tool.called"
    TOOL_RESULT = "tool.result"
    # Agent
    AGENT_THOUGHT = "agent.thought"
    # 社交
    SOCIAL_FRIEND_REQUEST = "social.friend_request"
    SOCIAL_MESSAGE = "social.message"
    # A2A
    A2A_CALL = "a2a.call"
    A2A_RESPONSE = "a2a.response"
    # 系统
    SYSTEM_ERROR = "system.error"
    SYSTEM_HEALTH = "system.health"


@dataclass
class Event:
    """事件对象"""
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)
    source: str = ""  # 事件来源模块

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
        }


# ── 订阅者条目 ──

@dataclass
class Subscription:
    """订阅信息"""
    callback: Callable
    subscriber_id: str
    event_type: str
    once: bool = False  # 是否只触发一次


class EventBus:
    """
    事件总线 —— 进程内发布/订阅

    线程安全，支持同步/异步分发。
    生产环境可替换为 Redis Pub/Sub 或 RabbitMQ。
    """

    def __init__(self, async_dispatch: bool = False, max_history: int = 1000):
        self._subscribers: Dict[str, List[Subscription]] = defaultdict(list)
        self._lock = threading.RLock()
        self._async = async_dispatch
        self._history: List[Event] = []
        self._max_history = max_history
        self._stats = {"emitted": 0, "dispatched": 0}

    # ── 订阅 API ──

    def on(self, event_type: str, callback: Callable = None, subscriber_id: str = None):
        """
        订阅事件（也支持装饰器语法）

        用法：
            # 直接订阅
            event_bus.on("memory.written", my_handler)

            # 装饰器
            @event_bus.on("memory.written")
            def on_memory(event):
                ...
        """
        def decorator(func: Callable) -> Callable:
            sid = subscriber_id or f"{func.__module__}.{func.__qualname__}"
            with self._lock:
                self._subscribers[event_type].append(
                    Subscription(callback=func, subscriber_id=sid, event_type=event_type)
                )
            return func

        if callback is not None:
            # 直接调用
            decorator(callback)
            return None
        # 装饰器模式
        return decorator

    def once(self, event_type: str, callback: Callable, subscriber_id: str = None):
        """订阅一次（触发后自动取消）"""
        sid = subscriber_id or f"once_{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._subscribers[event_type].append(
                Subscription(callback=callback, subscriber_id=sid, event_type=event_type, once=True)
            )

    def off(self, event_type: str, callback: Callable = None, subscriber_id: str = None):
        """取消订阅"""
        with self._lock:
            if event_type not in self._subscribers:
                return
            subs = self._subscribers[event_type]
            if callback:
                subs[:] = [s for s in subs if s.callback != callback]
            elif subscriber_id:
                subs[:] = [s for s in subs if s.subscriber_id != subscriber_id]
            else:
                # 取消该事件所有订阅
                subs.clear()

    # ── 发布 API ──

    def emit(self, event_type: str, data: Dict[str, Any] = None, source: str = "") -> Event:
        """
        发布事件

        Args:
            event_type: 事件类型
            data: 事件数据
            source: 来源模块名

        Returns:
            发布的事件对象
        """
        event = Event(event_type=event_type, data=data or {}, source=source)

        # 记录历史
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        self._stats["emitted"] += 1

        # 分发
        self._dispatch(event)

        return event

    def _dispatch(self, event: Event):
        """分发事件到所有订阅者"""
        with self._lock:
            subs = list(self._subscribers.get(event.event_type, []))

        if not subs:
            return

        for sub in subs:
            try:
                if self._async:
                    threading.Thread(target=sub.callback, args=(event,), daemon=True).start()
                else:
                    sub.callback(event)
                self._stats["dispatched"] += 1
            except Exception as e:
                logger.error(f"事件分发异常 [{sub.subscriber_id}]: {e}")
            finally:
                # once 订阅：触发后移除
                if sub.once:
                    self.off(event.event_type, subscriber_id=sub.subscriber_id)

    # ── 查询 API ──

    def get_history(self, event_type: str = None, limit: int = 100) -> List[Event]:
        """获取事件历史"""
        events = self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取总线统计"""
        return {
            **self._stats,
            "subscriber_count": sum(len(s) for s in self._subscribers.values()),
            "event_types": list(self._subscribers.keys()),
        }

    def clear(self):
        """清空所有订阅和历史"""
        with self._lock:
            self._subscribers.clear()
            self._history.clear()


# ── 全局单例 ──

_event_bus: Optional[EventBus] = None


def get_event_bus(async_dispatch: bool = False) -> EventBus:
    """获取全局 EventBus 实例"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus(async_dispatch=async_dispatch)
    return _event_bus


# ── 便捷函数 ──

def emit(event_type: str, data: Dict[str, Any] = None, source: str = "") -> Event:
    """便捷发布（使用全局总线）"""
    return get_event_bus().emit(event_type, data, source)


def on(event_type: str, callback: Callable = None, subscriber_id: str = None):
    """便捷订阅（使用全局总线）"""
    return get_event_bus().on(event_type, callback, subscriber_id)
