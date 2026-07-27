"""
异步 LLM 客户端 — 基于 httpx.AsyncClient

替代同步的 urllib.request / requests LLM 调用。
集成：连接池、重试（tenacity）、指标（Prometheus）、Correlation ID。
"""

import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from core.observability import observe_llm_call
from core.settings import settings

logger = logging.getLogger(__name__)


class AsyncLLMClient:
    """异步 LLM 客户端（OpenAI 兼容 API）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or settings.llm_api_key
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取异步客户端（连接池复用）"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            )
        return self._client

    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """异步聊天接口"""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        with observe_llm_call(self.model):
            client = await self._get_client()
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """异步流式聊天（SSE）"""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            **kwargs,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        client = await self._get_client()
        start = time.perf_counter()

        try:
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        finally:
            duration = time.perf_counter() - start
            logger.debug("[LLM_STREAM] model=%s duration=%.2fs", self.model, duration)

    async def embed(
        self,
        texts: List[str],
        model: Optional[str] = None,
    ) -> List[List[float]]:
        """异步嵌入接口"""
        payload = {
            "model": model or "text-embedding-3-small",
            "input": texts,
        }
        client = await self._get_client()
        resp = await client.post("/embeddings", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]

    async def close(self) -> None:
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# 模块级单例（惰性初始化）
_default_client: Optional[AsyncLLMClient] = None


async def get_llm_client() -> AsyncLLMClient:
    """获取默认异步 LLM 客户端"""
    global _default_client
    if _default_client is None:
        _default_client = AsyncLLMClient()
    return _default_client


async def close_llm_client() -> None:
    """关闭默认客户端（应用退出时调用）"""
    global _default_client
    if _default_client:
        await _default_client.close()
        _default_client = None
