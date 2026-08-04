"""
Tracing — Agent 链路追踪

为 Agent/Tool/LLM 调用提供分布式追踪能力。
设计原则：可选、零侵入、懒加载。

当 TRAACING_ENABLED=true 时启用 AgentOps 追踪。
默认关闭，不影响生产性能。
"""

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

# ── 可选依赖：AgentOps ──
try:
    import agentops

    _AGENTOPS_AVAILABLE = True
except ImportError:
    _AGENTOPS_AVAILABLE = False
    agentops = None


# ── 轻量本地追踪（始终可用，不依赖外部服务） ──

class TraceSpan:
    """单个追踪跨度"""

    __slots__ = ("name", "start_time", "end_time", "tags", "events")

    def __init__(self, name: str, tags: Optional[Dict[str, str]] = None):
        self.name = name
        self.start_time = time.perf_counter()
        self.end_time: Optional[float] = None
        self.tags = tags or {}
        self.events: List[Dict[str, Any]] = []

    def end(self, status: str = "ok") -> None:
        self.end_time = time.perf_counter()
        self.tags["status"] = status
        self.tags["duration_ms"] = f"{(self.end_time - self.start_time) * 1000:.1f}"

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.perf_counter() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "tags": self.tags,
            "events": self.events,
        }


class TraceCollector:
    """收集当前会话的追踪跨度"""

    def __init__(self, alpha_id: str = ""):
        self.alpha_id = alpha_id
        self.spans: List[TraceSpan] = []
        self._enabled = True

    def span(self, name: str, tags: Optional[Dict[str, str]] = None) -> TraceSpan:
        span = TraceSpan(name, tags)
        self.spans.append(span)
        return span

    def disable(self) -> None:
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_summary(self) -> Dict[str, Any]:
        if not self.spans:
            return {"total_spans": 0}
        total_time = sum(s.duration_ms for s in self.spans)
        by_status: Dict[str, int] = {}
        for s in self.spans:
            status = s.tags.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1
        return {
            "alpha_id": self.alpha_id,
            "total_spans": len(self.spans),
            "total_duration_ms": f"{total_time:.1f}",
            "by_status": by_status,
            "spans": [s.to_dict() for s in self.spans],
        }

    def clear(self) -> None:
        self.spans.clear()


# ── 全局收集器（线程安全用 thread-local） ──
import threading

_collector_local = threading.local()


def get_collector(alpha_id: str = "") -> TraceCollector:
    """获取当前线程的 TraceCollector"""
    collector = getattr(_collector_local, "collector", None)
    if collector is None:
        collector = TraceCollector(alpha_id)
        _collector_local.collector = collector
    return collector


def set_collector(collector: TraceCollector) -> None:
    """设置当前线程的 TraceCollector"""
    _collector_local.collector = collector


def reset_collector() -> None:
    """重置当前线程的 TraceCollector"""
    _collector_local.collector = None


@contextmanager
def trace_span(name: str, **tags: str) -> Generator[TraceSpan, None, None]:
    """上下文管理器：追踪一个操作的生命周期"""
    collector = get_collector()
    if not collector.enabled:
        span = TraceSpan(name, tags)
        span.end("ok")
        yield span
        return

    span = collector.span(name, tags)

    # AgentOps 集成（如果可用且已初始化）
    if _AGENTOPS_AVAILABLE and agentops and agentops.is_initialized():
        try:
            agentops.start_action(name=name, tags=tags)
        except Exception:
            pass

    status = "ok"
    try:
        yield span
    except Exception as e:
        status = "error"
        span.events.append({"type": "error", "message": str(e)})
        raise
    finally:
        span.end(status)
        if _AGENTOPS_AVAILABLE and agentops and agentops.is_initialized():
            try:
                agentops.end_action(status=status)
            except Exception:
                pass


# ── AgentOps 生命周期管理 ──

def init_agentops(api_key: Optional[str] = None) -> bool:
    """初始化 AgentOps 追踪（可选）"""
    if not _AGENTOPS_AVAILABLE:
        logger.info("AgentOps not installed — tracing limited to local collection")
        return False

    if not api_key:
        logger.info("AgentOps API key not set — tracing disabled")
        return False

    try:
        agentops.init(api_key=api_key)
        logger.info("AgentOps tracing initialized")
        return True
    except Exception as e:
        logger.warning("AgentOps init failed: %s", e)
        return False


def end_session() -> None:
    """结束当前 AgentOps 会话"""
    if _AGENTOPS_AVAILABLE and agentops and agentops.is_initialized():
        try:
            agentops.end_session("Success")
        except Exception:
            pass