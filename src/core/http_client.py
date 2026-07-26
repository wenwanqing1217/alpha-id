"""
统一 HTTP 客户端 — 基于 httpx

替代散落的 urllib.request / requests 调用。
集成：连接池、重试（tenacity）、日志（structlog）、Correlation ID。
"""

import contextlib
import logging
import uuid
from typing import Any, Dict, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import settings

logger = logging.getLogger(__name__)

_client: Optional[httpx.Client] = None
_async_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.Client:
    """获取同步 HTTP 客户端（连接池复用）"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=httpx.Timeout(settings.llm_timeout or 30.0),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
            headers={
                "User-Agent": "Alpha-ID/0.3",
                "Accept": "application/json",
            },
        )
    return _client


def get_async_client() -> httpx.AsyncClient:
    """获取异步 HTTP 客户端（连接池复用）"""
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout or 30.0),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
            headers={
                "User-Agent": "Alpha-ID/0.3",
                "Accept": "application/json",
            },
        )
    return _async_client


def close_clients() -> None:
    """关闭所有 HTTP 客户端（应用退出时调用）"""
    global _client, _async_client
    if _client and not _client.is_closed:
        _client.close()
    if _async_client and not _async_client.is_closed:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_async_client.aclose())
            else:
                loop.run_until_complete(_async_client.aclose())
        except Exception:
            pass
    _client = None
    _async_client = None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1.0, max=10.0),
    reraise=True,
)
def request(
    method: str,
    url: str,
    *,
    json: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    correlation_id: Optional[str] = None,
    **kwargs: Any,
) -> httpx.Response:
    """统一同步 HTTP 请求（带重试和日志）

    Args:
        method: HTTP 方法 (GET, POST, ...)
        url: 请求 URL
        json: JSON body
        headers: 额外请求头
        timeout: 超时覆盖（秒）
        correlation_id: 关联 ID（自动生成如未提供）
    """
    cid = correlation_id or str(uuid.uuid4())[:8]
    req_headers = headers or {}
    req_headers.setdefault("X-Request-ID", cid)

    client = get_client()
    with _log_request(method, url, cid):
        resp = client.request(
            method,
            url,
            json=json,
            headers=req_headers,
            timeout=timeout or settings.llm_timeout or 30.0,
            **kwargs,
        )
        resp.raise_for_status()
        return resp


async def arequest(
    method: str,
    url: str,
    *,
    json: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    correlation_id: Optional[str] = None,
    **kwargs: Any,
) -> httpx.Response:
    """统一异步 HTTP 请求（带日志）"""
    cid = correlation_id or str(uuid.uuid4())[:8]
    req_headers = headers or {}
    req_headers.setdefault("X-Request-ID", cid)

    client = get_async_client()
    with _log_request(method, url, cid):
        resp = await client.request(
            method,
            url,
            json=json,
            headers=req_headers,
            timeout=timeout or settings.llm_timeout or 30.0,
            **kwargs,
        )
        resp.raise_for_status()
        return resp


@contextlib.contextmanager
def _log_request(method: str, url: str, cid: str):
    """请求日志上下文管理器"""
    import time
    start = time.perf_counter()
    logger.debug(f"[HTTP] {method} {url} (id={cid})")
    try:
        yield
    except Exception:
        elapsed = time.perf_counter() - start
        logger.warning(f"[HTTP] {method} {url} FAILED after {elapsed:.2f}s (id={cid})")
        raise
    else:
        elapsed = time.perf_counter() - start
        logger.debug(f"[HTTP] {method} {url} OK in {elapsed:.2f}s (id={cid})")


def get_json(url: str, **kwargs: Any) -> Dict[str, Any]:
    """快捷 GET + JSON 解析"""
    resp = request("GET", url, **kwargs)
    return resp.json()


def post_json(url: str, json: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    """快捷 POST + JSON 解析"""
    resp = request("POST", url, json=json, **kwargs)
    return resp.json()
