"""Rate limiting middleware — 基于 limits 库 (FixedWindow)

全局 IP 级限流，防止暴力破解和 DoS。
通过 core.settings 配置，支持启用/禁用和自定义 RPM。
"""

from __future__ import annotations

import logging

from limits import RateLimitItemPerMinute, storage
from limits.strategies import FixedWindowRateLimiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.settings import settings

logger = logging.getLogger(__name__)


def _create_limiter() -> FixedWindowRateLimiter:
    """目前使用内存后端（单实例部署足够）。未来可扩展 Redis。"""
    return FixedWindowRateLimiter(storage.MemoryStorage())


_limiter = _create_limiter()


def _extract_client_ip(request: Request) -> str:
    """提取客户端真实 IP（支持反向代理场景）"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()

    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        return x_real_ip.strip()

    return request.client.host or "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """全局限流中间件 — IP 级 FixedWindow"""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        client_ip = _extract_client_ip(request)
        rpm = max(1, settings.rate_limit_requests_per_minute)
        limit = RateLimitItemPerMinute(rpm)

        try:
            if not _limiter.hit(limit, client_ip):
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": f"Too many requests. Limit: {rpm} per minute.",
                        "retry_after": 60,
                    },
                    headers={"Retry-After": "60"},
                )
        except Exception as exc:
            logger.error("Rate limiter error: %s", exc)
            # 限流出错时放行，避免误杀
            return await call_next(request)

        return await call_next(request)
