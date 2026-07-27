"""
可观测性 — Prometheus 指标 + 健康检查

提供：
- HTTP 请求计数 / 延迟分布
- LLM 调用成功率 / 耗时
- DB 操作计数
- 自定义业务指标
- /metrics 端点（Prometheus 抓取）
- /health（liveness）
- /ready（readiness，检查依赖）
"""

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        REGISTRY,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    generate_latest = None
    CONTENT_TYPE_LATEST = "text/plain"

# ── 指标定义 ──

if _PROMETHEUS_AVAILABLE:
    HTTP_REQUESTS = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )
    HTTP_LATENCY = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency",
        ["method", "endpoint"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    LLM_CALLS = Counter(
        "llm_calls_total",
        "Total LLM API calls",
        ["model", "status"],
    )
    LLM_LATENCY = Histogram(
        "llm_call_duration_seconds",
        "LLM call latency",
        ["model"],
        buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    )
    LLM_TOKENS = Counter(
        "llm_tokens_total",
        "Total tokens consumed",
        ["model", "type"],  # type: prompt / completion
    )
    DB_OPERATIONS = Counter(
        "db_operations_total",
        "Total DB operations",
        ["operation", "status"],
    )
    ACTIVE_USERS = Gauge(
        "active_users",
        "Currently active users",
    )
    MEMORY_STORE_SIZE = Gauge(
        "memory_store_size",
        "Number of memories stored",
        ["alpha_id"],
    )
else:
    # 桩对象，无 prometheus_client 时也能运行
    class _Stub:
        def labels(self, *a, **k):
            return self
        def inc(self, *a, **k):
            pass
        def observe(self, *a, **k):
            pass
        def set(self, *a, **k):
            pass
        def time(self):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    HTTP_REQUESTS = HTTP_LATENCY = LLM_CALLS = LLM_LATENCY = _Stub()
    LLM_TOKENS = DB_OPERATIONS = ACTIVE_USERS = MEMORY_STORE_SIZE = _Stub()


def record_http_request(method: str, endpoint: str, status: int, duration: float) -> None:
    """记录一次 HTTP 请求"""
    HTTP_REQUESTS.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    HTTP_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)


def record_llm_call(model: str, success: bool, duration: float, tokens: int = 0) -> None:
    """记录一次 LLM 调用"""
    status = "success" if success else "failure"
    LLM_CALLS.labels(model=model, status=status).inc()
    LLM_LATENCY.labels(model=model).observe(duration)
    if tokens > 0:
        LLM_TOKENS.labels(model=model, type="completion").inc(tokens)


def record_db_op(operation: str, success: bool = True) -> None:
    """记录一次 DB 操作"""
    DB_OPERATIONS.labels(operation=operation, status="success" if success else "failure").inc()


@contextmanager
def observe_llm_call(model: str):
    """LLM 调用计时上下文管理器"""
    start = time.perf_counter()
    success = True
    try:
        yield
    except Exception:
        success = False
        raise
    finally:
        duration = time.perf_counter() - start
        record_llm_call(model, success, duration)


def get_metrics() -> bytes:
    """获取 Prometheus 指标数据（用于 /metrics 端点）"""
    if not _PROMETHEUS_AVAILABLE:
        return b"# prometheus_client not installed\n"
    return generate_latest()


def metrics_content_type() -> str:
    """获取 metrics 响应的 Content-Type"""
    return CONTENT_TYPE_LATEST


# ── 健康检查 ──

def check_liveness() -> Dict[str, Any]:
    """存活检查（进程是否在跑）"""
    from core.settings import settings
    return {
        "status": "ok",
        "service": "alpha-id",
        "version": settings.app_version,
        "timestamp": time.time(),
    }


def check_readiness() -> Dict[str, Any]:
    """就绪检查（依赖是否可用）"""
    checks: Dict[str, str] = {}
    all_ok = True

    # 检查 SQLite
    try:
        from core.settings import settings
        from core.storage_sqlite import SqliteStorage
        store = SqliteStorage()
        store.load("__health_check__")
        store.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        all_ok = False

    # 检查 LLM 配置（不实际调用，只看是否配置）
    try:
        from core.settings import settings
        if settings.llm_api_key:
            checks["llm"] = "configured"
        else:
            checks["llm"] = "not_configured"
            # 未配置不算 not ready，因为可能走演示模式
    except Exception as e:
        checks["llm"] = f"error: {e}"

    # 检查 ChromaDB
    try:
        import chromadb  # noqa: F401
        checks["vector_db"] = "ok"
    except ImportError:
        checks["vector_db"] = "not_installed"

    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "timestamp": time.time(),
    }
