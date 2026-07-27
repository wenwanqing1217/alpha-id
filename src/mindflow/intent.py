"""
MindFlow 意图识别器

基于关键词规则 + LLM 回退的轻量意图分类。
从 aid_core 迁移而来，整合到 mindflow 模块中。

用法：
    from mindflow.intent import IntentClassifier

    classifier = IntentClassifier()
    result = classifier.classify("明天9点去公司开会")
    print(result.intent)  # "chat" / "route_plan" / ...
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.settings import settings

logger = logging.getLogger("mindflow.intent")


@dataclass
class IntentResult:
    """意图识别结果"""
    intent: str
    confidence: float = 0.0
    params: Dict[str, Any] = field(default_factory=dict)
    tools_needed: List[str] = field(default_factory=list)


# ── LLM 意图识别配置（通过 settings 统一读取） ──
_LLM_API_KEY = settings.llm_api_key
_LLM_BASE_URL = settings.llm_base_url
_LLM_MODEL = settings.llm_model
_LLM_ENABLED = bool(_LLM_API_KEY)

_INTENT_DEFINITIONS = {
    "route_plan": "路线/导航/出行规划",
    "navigate_to": "去某个具体地点",
    "interview_prep": "面试/简历/求职准备",
    "calendar_query": "日程/日历查询",
    "weather_query": "天气查询",
    "resume": "简历/CV相关",
    "search": "信息搜索/查询",
    "code_runner": "编程/写代码/脚本/开发",
    "codex_agent": "调 Codex 终端执行复杂任务",
    "ghost_identity": "身份注册/绑定",
    "chat": "日常对话/闲聊/其他",
}

# ── 关键词规则表 ──

_KEYWORD_RULES = [
    # (意图, 关键词列表, 需要的工具, 置信度)
    ("ghost_identity", ["我是谁", "注册身份", "绑定身份", "激活", "你是谁"], [], 0.9),
    ("route_plan", ["路线", "导航", "怎么去", "怎么走", "从", "到", "出行", "开车", "地铁"], ["baidu_map"], 0.85),
    ("route_plan", ["规划", "行程", "路线规划", "导航到"], ["baidu_map", "route_plan"], 0.9),
    ("navigate_to", ["我要去", "我去", "带我去", "导航到", "搜索附近", "找附近", "最近的"], ["place_search", "baidu_map"], 0.9),
    ("interview_prep", ["面试", "简历", "准备面试", "面经", "跳槽", "求职"], ["resume_engine", "company_db"], 0.85),
    ("calendar_query", ["日程", "日历", "今天有什么", "下周", "安排", "行程表"], ["calendar"], 0.8),
    ("weather_query", ["天气", "气温", "下雨", "刮风", "温度", "穿什么"], ["weather_api"], 0.9),
    ("resume", ["简历", "CV", "求职信", "作品集"], ["resume_engine"], 0.8),
    ("search", ["搜索", "查一下", "搜一下", "帮我查", "查询", "百度"], ["web_search"], 0.75),
    ("code_runner", ["编程", "写代码", "改代码", "debug", "重构", "写个", "帮我写", "代码", "脚本", "程序"], ["code_runner"], 0.85),
    ("code_runner", ["Python", "JavaScript", "Go", "Rust", "Java", "C++", "前端", "后端", "API", "爬虫"], ["code_runner"], 0.75),
]

# 工具自动推断映射
_INTENT_TOOLS = {
    "route_plan": ["baidu_map"],
    "interview_prep": ["company_db", "calendar"],
    "calendar_query": ["calendar"],
    "weather_query": ["weather_api"],
    "resume": ["resume_engine"],
    "search": ["web_search"],
    "code_runner": ["code_runner"],
    "codex_agent": ["codex_agent"],
}

# LLM 意图识别提示词
_LLM_SYSTEM_PROMPT = """你是一个意图分类器。根据用户消息，从以下意图中选择最匹配的一个：
{intent_list}

规则：
- 编程相关需求（写代码、改bug、写脚本、开发功能等）→ code_runner
- 日常对话、打招呼、闲聊 → chat
- 不确定时选 chat

只返回一个 JSON：{"intent": "意图名", "confidence": 0.0~1.0}
不要多余文字。"""



class IntentClassifier:
    """意图识别器：关键词优先，LLM 回退"""

    def __init__(self):
        pass

    def classify(self, text: str) -> IntentResult:
        """识别用户消息的意图：关键词优先 + LLM 回退"""
        # 1. 关键词快速匹配
        result = self._keyword_match(text)
        if result and result.confidence >= 0.85:
            return result

        # 2. LLM 识别（更准）
        if _LLM_ENABLED:
            try:
                llm_result = self._llm_classify(text)
                if llm_result and llm_result.confidence >= 0.6:
                    logger.info("LLM 意图: %s (%.2f) <- %s", llm_result.intent, llm_result.confidence, text[:30])
                    return llm_result
            except Exception as e:
                logger.warning("LLM 意图分类失败: %s", e)

        # 3. 降级：关键词结果或默认
        return result or IntentResult(intent="chat", confidence=0.5, tools_needed=[])

    def _keyword_match(self, text: str) -> Optional[IntentResult]:
        """关键词规则匹配"""
        text_lower = text.lower()
        for intent, keywords, tools, conf in _KEYWORD_RULES:
            if any(kw in text_lower for kw in keywords):
                return IntentResult(
                    intent=intent,
                    confidence=conf,
                    params={"keyword_matched": True},
                    tools_needed=tools,
                )
        return None

