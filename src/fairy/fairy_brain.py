"""
NURO 大脑 — MiniCPM-o-4.5 多模态推理引擎

通过 Ollama 本地推理，支持文本 + 图像输入。
VRAM 预算：~5.5GB（Q4_K_M 量化）
"""

import base64
import logging
import time
from typing import Optional, List

import httpx

from core.settings import settings

logger = logging.getLogger(__name__)

OLLAMA_HOST = settings.ollama_url
DEFAULT_MODEL = settings.fairy_model


class FairyBrain:
    """MiniCPM-o-4.5 多模态推理引擎"""

    def __init__(self, model: str = DEFAULT_MODEL, timeout: int = 120,
                 system_prompt: Optional[str] = None,
                 memory_context: Optional[List[str]] = None):
        self.model = model
        self.timeout = timeout
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.memory_context = memory_context or []
        self._client = httpx.Client(timeout=timeout)
        logger.info(f"FairyBrain 初始化: model={model}")

    @staticmethod
    def _default_system_prompt() -> str:
        return """你是 NURO，一个纯本地 AI 桌面宠物。
- 中文为主，偶尔夹英文
- 幽默但不刻薄，像一个毒舌但关心人的朋友
- 回答简洁，不要长篇大论
- 保护用户隐私，不泄露任何本地数据
- 你可以观察用户的屏幕活动（除非进入眼瞎耳聋模式）"""

    @property
    def available(self) -> bool:
        """检查 Ollama 是否运行且有模型"""
        try:
            resp = self._client.get(f"{OLLAMA_HOST}/api/tags")
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return any(self.model.split(":")[0] in m for m in models)
        except Exception:
            return False

    @property
    def is_available(self) -> bool:
        """别名（兼容多种调用风格）"""
        return self.available

    def generate(self, prompt: str, image_path: Optional[str] = None,
                 system: Optional[str] = None, max_tokens: int = 512) -> str:
        """
        生成回复

        Args:
            prompt: 用户输入
            image_path: 图片路径（可选，多模态）
            system: 系统提示词（覆盖默认）
            max_tokens: 最大生成 token 数

        Returns:
            模型回复文本
        """
        messages = []
        sys_prompt = system or self.system_prompt

        # 注入记忆上下文
        if self.memory_context:
            memory_text = "\n".join(f"- {m}" for m in self.memory_context[:5])
            sys_prompt += f"\n\n[用户记忆]\n{memory_text}"

        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})

        if image_path and os.path.exists(image_path):
            # 多模态：文本 + 图片
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            messages.append({
                "role": "user",
                "content": prompt,
                "images": [img_b64]
            })
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7,
            }
        }

        start = time.time()
        try:
            resp = self._client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
            resp.raise_for_status()
            result = resp.json()
            text = result.get("message", {}).get("content", "")
            elapsed = time.time() - start
            logger.debug(f"推理完成: {elapsed:.1f}s, {len(text)} chars")
            return text
        except Exception as e:
            logger.error(f"推理失败: {e}")
            return ""

    def describe_image(self, image_path: str, prompt: str = "详细描述这张图片") -> str:
        """描述图片内容（Computer Use 视觉）"""
        return self.generate(prompt, image_path=image_path, max_tokens=1024)

    def close(self):
        self._client.close()

    def __repr__(self):
        return f"<FairyBrain model={self.model}>"
