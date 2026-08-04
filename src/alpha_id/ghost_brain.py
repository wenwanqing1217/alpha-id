# TERM: GhostBrain — 桌面精灵大脑（通过 Gateway 统一接口进行对话，支持本地 Ollama 推理）
"""
NURO Ghost — Ghost Platform 桌面精灵大脑

通过 Gateway 统一接口进行对话，同时支持本地 Ollama 推理。
"""

import logging
import time
from typing import Optional, List

import httpx

from core.settings import settings

logger = logging.getLogger(__name__)

GATEWAY_URL = settings.gateway_url or "http://localhost:18080"
OLLAMA_HOST = settings.ollama_url or "http://localhost:11434"
DEFAULT_MODEL = settings.fairy_model or "minicpm-o:4.5-4bit"


class GhostBrain:
    """
    Ghost Platform 大脑 — Gateway 聊天 + 本地 Ollama 推理

    优先使用 Gateway /v1/human/chat（与前端统一），
    Gateway 不可用时回退到本地 Ollama。
    """

    def __init__(self, gateway_url: str = GATEWAY_URL, model: str = DEFAULT_MODEL):
        self.gateway_url = gateway_url
        self.model = model
        self._client = httpx.Client(timeout=60)
        self._alpha_id = "Alpha-001"
        logger.info(f"GhostBrain 初始化: gateway={gateway_url}, model={model}")

    @property
    def available(self) -> bool:
        """检查 Gateway 是否可达"""
        try:
            resp = self._client.get(f"{self.gateway_url}/health", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    @property
    def is_available(self) -> bool:
        """别名（兼容多种调用风格）"""
        return self.available

    def set_alpha_id(self, alpha_id: str):
        """设置当前 Alpha-ID"""
        self._alpha_id = alpha_id

    def chat(self, message: str, max_tokens: int = 512) -> str:
        """
        与 Ghost Platform 对话

        优先走 Gateway /v1/human/chat（与前端 DS 统一），
        Gateway 不可用时回退到 Ollama 本地推理。
        """
        # 优先 Gateway
        if self.available:
            try:
                resp = self._client.post(
                    f"{self.gateway_url}/v1/human/chat",
                    json={"message": message, "alpha_id": self._alpha_id},
                    timeout=30,
                )
                data = resp.json()
                reply = data.get("data", {}).get("reply") or data.get("reply")
                if reply:
                    return reply
            except Exception as e:
                logger.warning(f"Gateway 聊天失败，回退到 Ollama: {e}")

        # 回退到 Ollama
        return self._ollama_chat(message, max_tokens)

    def _ollama_chat(self, message: str, max_tokens: int) -> str:
        """本地 Ollama 推理"""
        try:
            resp = self._client.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "你是 NURO Ghost，Ghost Platform 的桌面精灵助手。中文为主，简洁幽默。"},
                        {"role": "user", "content": message},
                    ],
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": 0.7},
                },
                timeout=60,
            )
            result = resp.json()
            return result.get("message", {}).get("content", "") or "（沉默...）"
        except Exception as e:
            logger.error(f"Ollama 推理失败: {e}")
            return "大脑离线了 😵"

    def describe_image(self, image_path: str, prompt: str = "描述这张图片") -> str:
        """描述图片（多模态）"""
        import base64
        import os

        if not os.path.exists(image_path):
            return "图片不存在"

        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()

            # 尝试通过 Gateway
            if self.available:
                resp = self._client.post(
                    f"{self.gateway_url}/v1/human/chat",
                    json={
                        "message": prompt,
                        "alpha_id": self._alpha_id,
                        "image": img_b64,
                    },
                    timeout=30,
                )
                data = resp.json()
                reply = data.get("data", {}).get("reply") or data.get("reply")
                if reply:
                    return reply

            # 回退到 Ollama
            resp = self._client.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt, "images": [img_b64]},
                    ],
                    "stream": False,
                },
                timeout=60,
            )
            result = resp.json()
            return result.get("message", {}).get("content", "") or "看不清..."
        except Exception as e:
            logger.error(f"图片描述失败: {e}")
            return "视觉模块离线了 👁️"

    def close(self):
        """关闭 HTTP 客户端"""
        try:
            self._client.close()
        except Exception:
            pass

    def __repr__(self):
        return f"<GhostBrain gateway={self.gateway_url} model={self.model}>"
