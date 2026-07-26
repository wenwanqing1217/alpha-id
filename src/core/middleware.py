"""
Correlation ID + Prometheus 指标中间件

贯穿整个请求生命周期：
- HTTP 请求入口生成/提取 request_id
- 注入到 structlog 日志上下文
- 传递到下游 HTTP 调用（X-Request-ID header）
- 写入 HTTP 响应头，方便客户端追踪
- 记录 Prometheus 指标（请求计数 + 延迟分布）
"""

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from core.observability import HTTP_REQUESTS, HTTP_LATENCY

logger = logging.getLogger(__name__)

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """获取当前请求的 request_id"""
    return _request_id_var.get()


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求注入 Correlation ID + 记录 Prometheus 指标"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:12]
        token = _request_id_var.set(request_id)

        # 注入到 request state，供路由处理器访问
        request.state.request_id = request_id

        start = time.perf_counter()
        endpoint = request.url.path

        logger.debug(
            f"[REQUEST] {request.method} {endpoint} id={request_id} "
            f"client={request.client.host if request.client else 'unknown'}"
        )

        try:
            response = await call_next(request)
            duration = time.perf_counter() - start

            # Prometheus 指标埋点
            HTTP_REQUESTS.labels(
                method=request.method,
                endpoint=endpoint,
                status=str(response.status_code),
            ).inc()
            HTTP_LATENCY.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(duration)

            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            duration = time.perf_counter() - start
            HTTP_REQUESTS.labels(
                method=request.method,
                endpoint=endpoint,
                status="500",
            ).inc()
            HTTP_LATENCY.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(duration)

            logger.error(
                f"[REQUEST_ERROR] {request.method} {endpoint} "
                f"id={request_id} error={exc}"
            )
            raise
        finally:
            _request_id_var.reset(token)


def get_correlation_id() -> str:
    """获取当前上下文的关联 ID（供业务代码调用）"""
    return _request_id_var.get() or "no-context"
