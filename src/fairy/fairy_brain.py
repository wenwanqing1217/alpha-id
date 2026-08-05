"""
NURO Ghost — Ghost Platform 大脑（Gateway 优先 + Ollama 回退）

优先使用 Gateway /v1/human/chat（与前端 DS 统一），
Gateway 不可用时回退到本地 Ollama 推理。
"""

import base64
import logging
import os
from typing import List, Optional

import httpx

from core.settings import settings

logger = logging.getLogger(__name__)

GATEWAY_URL = settings.gateway_url
OLLAMA_HOST = settings.ollama_url
DEFAULT_MODEL = settings.fairy_model


class FairyBrain:
    """
    Ghost Platform 大脑 — Gateway 聊天 + 本地 Ollama 推理

    保持 FairyBrain 类名兼容旧代码（app.py 导入路径不变）。
    """

    def __init__(self, model: str = DEFAULT_MODEL, timeout: int = 120,
                 system_prompt: Optional[str] = None,
                 memory_context: Optional[List[str]] = None):
        self.model = model
        self.timeout = timeout
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.memory_context = memory_context or []
        self._client = httpx.Client(timeout=timeout)
        self._alpha_id = "Alpha-001"
        logger.info(f"GhostBrain 初始化: gateway={GATEWAY_URL}, model={model}")

    @staticmethod
    def _default_system_prompt() -> str:
        return """你是 NURO Ghost，Ghost Platform 的桌面精灵助手。
- 中文为主，偶尔夹英文
- 简洁幽默，像一个关心人的朋友
- 保护用户隐私，不泄露任何本地数据"""

    @property
    def available(self) -> bool:
        """检查 Gateway 是否可达"""
        try:
            resp = self._client.get(f"{GATEWAY_URL}/health", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    @property
    def is_available(self) -> bool:
        return self.available

    def set_alpha_id(self, alpha_id: str):
        self._alpha_id = alpha_id

    def chat(self, message: str, max_tokens: int = 512) -> str:
        """
        与 Ghost Platform 对话

        优先走 Gateway /v1/human/chat，
        Gateway 不可用时回退到 Ollama 本地推理。
        """
        if self.available:
            try:
                resp = self._client.post(
                    f"{GATEWAY_URL}/v1/human/chat",
                    json={"message": message, "alpha_id": self._alpha_id},
                    timeout=30,
                )
                data = resp.json()
                reply = data.get("data", {}).get("reply") or data.get("reply")
                if reply:
                    return reply
            except Exception as e:
                logger.warning(f"Gateway 聊天失败，回退到 Ollama: {e}")

        return self._ollama_chat(message, max_tokens)

    def _ollama_chat(self, message: str, max_tokens: int) -> str:
        """本地 Ollama 推理"""
        try:
            messages = []
            if self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})
            if self.memory_context:
                mem_text = "\n".join(f"- {m}" for m in self.memory_context[:5])
                messages.append({"role": "system", "content": f"[用户记忆]\n{mem_text}"})
            messages.append({"role": "user", "content": message})

            resp = self._client.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
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

    def generate(self, prompt: str, image_path: Optional[str] = None,
                 system: Optional[str] = None, max_tokens: int = 512) -> str:
        """生成回复（兼容旧接口）"""
        sys = system or self.system_prompt
        if image_path and os.path.exists(image_path):
            return self._ollama_chat_with_image(prompt, image_path, max_tokens)
        if sys:
            full_prompt = f"[系统提示]\n{sys}\n\n[用户输入]\n{prompt}"
            return self.chat(full_prompt, max_tokens)
        return self.chat(prompt, max_tokens)

    def _ollama_chat_with_image(self, prompt: str, image_path: str, max_tokens: int) -> str:
        """多模态推理"""
        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            resp = self._client.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt, "images": [img_b64]}],
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
                timeout=60,
            )
            result = resp.json()
            return result.get("message", {}).get("content", "") or "看不清..."
        except Exception as e:
            logger.error(f"多模态推理失败: {e}")
            return "视觉模块离线了 👁️"

    def describe_image(self, image_path: str, prompt: str = "详细描述这张图片") -> str:
        """描述图片（兼容旧接口）"""
        return self._ollama_chat_with_image(prompt, image_path, 1024)

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass

    def __repr__(self):
        return f"<FairyBrain gateway={GATEWAY_URL} model={self.model}>"
