"""
Alpha-ID LLM Enricher — 核心理解引擎
======================================
把原始对话文本变成结构化画像的统一入口。

设计原则：
  - 数据进来：任何来源的原始对话文本
  - 理解处理：LiteLLM 路由，免费额度优先
  - 数据出去：结构化 JSON，直接写入本地存储
  - 数据归谁：你的电脑，不是任何第三方

使用方式：
  enricher = LLMEnricher()
  profile_data = enricher.analyze(conversation_text, source="doubao")
  # profile_data 是结构化 dict，可直接存 SQLite / 合并到 AID 画像
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── 分析 Prompt 模板 ──────────────────────────────────────────────

ANALYSIS_PROMPT = """你是一个专业的用户画像分析引擎。请分析以下对话内容，提取用户的结构化画像信息。

【要求】
1. 只提取有证据的信息，不要猜测
2. 技术栈要具体到语言/框架/工具层面
3. 熟练度分五级：beginner / intermediate / advanced / expert / unknown
4. 如果对话中没有相关信息，该字段留 null
5. 输出纯 JSON，不要 markdown 代码块

【对话内容】
{conversation}

【输出格式】
{{
  "technical": {{
    "languages": {{"python": "advanced", "typescript": "intermediate"}},
    "frameworks": ["fastapi", "react", "vue"],
    "tools": ["docker", "git", "cursor"],
    "domains": ["backend", "api-gateway", "ai-agent"],
    "current_projects": ["Ghost Gateway - FastAPI 统一 API 网关"],
    "learning": ["rust", "mcp-protocol"]
  }},
  "communication": {{
    "tone": "direct",
    "style": "structured-thinking",
    "languages": ["chinese", "english-technical"],
    "sentence_length": "medium"
  }},
  "work_pattern": {{
    "rhythm": "night_owl",
    "peak_hours": [22, 23, 0, 1],
    "commit_frequency": "daily",
    "recent_focus": "gateway refactoring"
  }},
  "thinking": {{
    "approach": "problem-solution-oriented",
    "depth": "deep",
    "breadth": "broad"
  }},
  "evidence": {{
    "languages": "从对话第 3 轮提到 FastAPI 和 Python 项目",
    "domains": "多次讨论 API 网关、限流、CORS"
  }}
}}"""


class LLMEnricher:
    """
    LLM 理解引擎 — 把原始文本变成结构化画像。
    
    路由策略（免费优先）：
      1. Gemini (google/gemini-2.0-flash) — 免费额度
      2. DeepSeek (deepseek/deepseek-chat) — ¥1/M tokens
      3. 其他 LiteLLM 支持的模型
    """

    # 模型优先级（免费 → 低价 → 兜底）
    MODEL_PRIORITY = [
        "gemini/gemini-2.0-flash",
        "deepseek/deepseek-chat",
        "openrouter/google/gemini-2.0-flash-001",
    ]

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        """
        初始化 Enricher。
        
        Args:
            model: 指定模型，不指定则按优先级自动选
            api_key: API key，不指定则从环境变量读取
        """
        self.model = model or self._auto_select_model()
        self.api_key = api_key
        self._call_count = 0
        self._total_tokens = 0
        logger.info("LLMEnricher 初始化 — 模型: %s", self.model)

    def _auto_select_model(self) -> str:
        """根据环境变量自动选择可用模型（免费优先）"""
        # 检查 Gemini
        if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
            return "gemini/gemini-2.0-flash"
        # 检查 DeepSeek
        if os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY"):
            return "deepseek/deepseek-chat"
        # 检查 OpenRouter（聚合多家，部分免费）
        if os.getenv("OPENROUTER_API_KEY"):
            return "openrouter/google/gemini-2.0-flash-001"
        # 默认 DeepSeek（最便宜）
        return "deepseek/deepseek-chat"

    def analyze(self, conversation: str, source: str = "unknown") -> Dict[str, Any]:
        """
        分析对话内容，返回结构化画像数据。
        
        Args:
            conversation: 原始对话文本
            source: 数据来源标识（doubao / chatgpt / cursor / manual）
            
        Returns:
            结构化画像 dict
        """
        if not conversation or len(conversation.strip()) < 50:
            logger.warning("对话内容太短（< 50 字符），跳过分析")
            return self._empty_result(source)

        prompt = ANALYSIS_PROMPT.format(conversation=conversation[:8000])

        try:
            result = self._call_llm(prompt)
            parsed = self._parse_response(result)
            parsed["_meta"] = {
                "source": source,
                "model": self.model,
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "input_length": len(conversation),
            }
            self._call_count += 1
            logger.info("分析完成 — 来源: %s, 模型: %s", source, self.model)
            return parsed

        except Exception as e:
            logger.error("LLM 分析失败: %s", e)
            return self._empty_result(source, error=str(e))

    def analyze_batch(self, conversations: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        批量分析多条对话，合并结果。
        
        Args:
            conversations: [{"text": "...", "source": "doubao", "timestamp": "..."}]
            
        Returns:
            合并后的结构化画像
        """
        all_results = []
        for conv in conversations:
            result = self.analyze(conv["text"], source=conv.get("source", "unknown"))
            result["_meta"]["timestamp"] = conv.get("timestamp", "")
            all_results.append(result)

        return self._merge_results(all_results)

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM（通过 LiteLLM 或直接 API）"""
        try:
            # 优先尝试 LiteLLM
            import litellm

            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2004,
            )
            return response.choices[0].message.content

        except ImportError:
            # 没有 LiteLLM → 直接用 OpenAI 兼容 API
            return self._call_openai_compatible(prompt)

    def _call_openai_compatible(self, prompt: str) -> str:
        """直接调用 OpenAI 兼容 API（DeepSeek / OpenRouter 等）"""
        import httpx

        base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
        model_name = self.model.split("/")[-1] if "/" in self.model else self.model

        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2004,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON"""
        # 去掉可能的 markdown 代码块
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 部分
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def _merge_results(self, results: List[Dict]) -> Dict[str, Any]:
        """合并多个分析结果"""
        merged = {
            "technical": {
                "languages": {},
                "frameworks": [],
                "tools": [],
                "domains": [],
                "current_projects": [],
                "learning": [],
            },
            "communication": {
                "tone": None,
                "style": None,
                "languages": [],
                "sentence_length": None,
            },
            "work_pattern": {
                "rhythm": None,
                "peak_hours": [],
                "commit_frequency": None,
                "recent_focus": None,
            },
            "thinking": {
                "approach": None,
                "depth": None,
                "breadth": None,
            },
            "evidence": {},
            "_meta": {"sources": [], "merged_count": len(results)},
        }

        for r in results:
            if not r or "technical" not in r:
                continue

            # 技术栈合并（取最高熟练度）
            for lang, level in (r.get("technical", {}).get("languages", {}) or {}).items():
                existing = merged["technical"]["languages"].get(lang)
                if existing is None or self._level_value(level) > self._level_value(existing):
                    merged["technical"]["languages"][lang] = level

            # 列表字段合并去重
            for field in ["frameworks", "tools", "domains", "current_projects", "learning"]:
                existing = merged["technical"][field]
                new_items = (r.get("technical") or {}).get(field, []) or []
                merged["technical"][field] = list(dict.fromkeys(existing + new_items))

            # 沟通风格（多数表决）
            tone = (r.get("communication") or {}).get("tone")
            if tone and not merged["communication"]["tone"]:
                merged["communication"]["tone"] = tone

            # 证据收集
            evidence = r.get("evidence", {})
            if evidence:
                merged["evidence"].update(evidence)

            # 来源追踪
            source = (r.get("_meta") or {}).get("source", "unknown")
            if source not in merged["_meta"]["sources"]:
                merged["_meta"]["sources"].append(source)

        return merged

    @staticmethod
    def _level_value(level: str) -> int:
        """熟练度转数值"""
        return {
            "beginner": 1,
            "intermediate": 2,
            "advanced": 3,
            "expert": 4,
        }.get(str(level).lower(), 0)

    @staticmethod
    def _empty_result(source: str = "unknown", error: Optional[str] = None) -> Dict[str, Any]:
        """返回空结果模板"""
        return {
            "technical": {
                "languages": {},
                "frameworks": [],
                "tools": [],
                "domains": [],
                "current_projects": [],
                "learning": [],
            },
            "communication": {"tone": None, "style": None, "languages": [], "sentence_length": None},
            "work_pattern": {"rhythm": None, "peak_hours": [], "commit_frequency": None, "recent_focus": None},
            "thinking": {"approach": None, "depth": None, "breadth": None},
            "evidence": {},
            "_meta": {"source": source, "error": error, "analyzed_at": datetime.now(timezone.utc).isoformat()},
        }

    @property
    def stats(self) -> Dict[str, int]:
        """返回调用统计"""
        return {"call_count": self._call_count, "total_tokens": self._total_tokens}
