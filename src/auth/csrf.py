"""
CSRF 防护中间件 — 纵深防御

基于 Origin/Referer 头验证，阻止跨站伪造的状态变更请求。
与 Bearer Token 认证互补：Token 防未授权访问，CSRF 防跨站请求伪造。

防护策略：
  1. 安全方法（GET/HEAD/OPTIONS）直接放行
  2. 状态变更方法（POST/PUT/DELETE/PATCH）要求：
     a. Origin 头匹配允许的来源列表，或
     b. Referer 头匹配允许的来源列表（兼容无 Origin 的旧浏览器）
     c. 同时要求 X-Requested-With 头（浏览器跨域 fetch 无法设置自定义头）
  3. 无 Origin/Referer 头的请求直接拒绝（非浏览器客户端应显式设置）
"""

import logging
from typing import Optional, Set

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# 安全方法 — 不要求 CSRF 检查
_SAFE_METHODS: Set[str] = {"GET", "HEAD", "OPTIONS"}

# 自定义头 — 浏览器跨域 fetch 无法设置（需 CORS preflight 显式允许）
_CSRF_CUSTOM_HEADER = "X-Requested-With"
_CSRF_CUSTOM_HEADER_VALUE = "XMLHttpRequest"


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF 防护中间件 — 验证 Origin/Referer + 自定义头"""

    def __init__(
        self,
        app: ASGIApp,
        allowed_origins: Set[str],
        exempt_paths: Optional[Set[str]] = None,
        exempt_prefixes: Optional[Set[str]] = None,
        enforce_custom_header: bool = True,
    ) -> None:
        super().__init__(app)
        self._allowed_origins = allowed_origins
        self._exempt_paths = exempt_paths or set()
        self._exempt_prefixes = exempt_prefixes or set()
        self._enforce_custom_header = enforce_custom_header

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 安全方法直接放行
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        path = request.url.path

        # 豁免路径（如 webhook 回调、OAuth 回调等外部入口）
        # 支持精确匹配和前缀匹配（如 /api/v1/register/ 匹配所有注册接口）
        if path in self._exempt_paths:
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in self._exempt_prefixes):
            return await call_next(request)

        # 自定义头检查 — 浏览器跨域 fetch 无法设置自定义头
        if self._enforce_custom_header:
            requested_with = request.headers.get(_CSRF_CUSTOM_HEADER, "")
            if requested_with != _CSRF_CUSTOM_HEADER_VALUE:
                logger.warning(
                    "CSRF check failed: missing %s header (path=%s, method=%s)",
                    _CSRF_CUSTOM_HEADER,
                    path,
                    request.method,
                )
                return Response(
                    content='{"detail":"CSRF validation failed: missing X-Requested-With header"}',
                    status_code=403,
                    media_type="application/json",
                    headers={"X-CSRF-Error": "missing-custom-header"},
                )

        # Origin 头检查
        origin = request.headers.get("Origin")
        if origin:
            if origin not in self._allowed_origins:
                logger.warning(
                    "CSRF check failed: Origin not allowed (origin=%s, path=%s)",
                    origin,
                    path,
                )
                return Response(
                    content='{"detail":"CSRF validation failed: origin not allowed"}',
                    status_code=403,
                    media_type="application/json",
                    headers={"X-CSRF-Error": "origin-not-allowed"},
                )
            return await call_next(request)

        # Referer 头回退检查（兼容无 Origin 的场景）
        referer = request.headers.get("Referer")
        if referer:
            # 从完整 URL 提取 origin 部分
            from urllib.parse import urlparse

            parsed = urlparse(referer)
            referer_origin = f"{parsed.scheme}://{parsed.netloc}"
            if referer_origin not in self._allowed_origins:
                logger.warning(
                    "CSRF check failed: Referer not allowed (referer=%s, path=%s)",
                    referer,
                    path,
                )
                return Response(
                    content='{"detail":"CSRF validation failed: referer not allowed"}',
                    status_code=403,
                    media_type="application/json",
                    headers={"X-CSRF-Error": "referer-not-allowed"},
                )
            return await call_next(request)

        # 无 Origin 也无 Referer — 拒绝（非浏览器客户端应显式设置）
        logger.warning(
            "CSRF check failed: no Origin or Referer header (path=%s, method=%s, client=%s)",
            path,
            request.method,
            request.client,
        )
        return Response(
            content='{"detail":"CSRF validation failed: missing Origin/Referer header"}',
            status_code=403,
            media_type="application/json",
            headers={"X-CSRF-Error": "missing-origin-referer"},
        )
