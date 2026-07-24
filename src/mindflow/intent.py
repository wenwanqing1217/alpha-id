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
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mindflow.intent")


@dataclass
class IntentResult:
    """意图识别结果"""
    intent: str
    confidence: float = 0.0
    params: Dict[str, Any] = field(default_factory=dict)
    tools_needed: List[str] = field(default_factory=list)


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
]

# 工具自动推断映射
_INTENT_TOOLS = {
    "route_plan": ["baidu_map"],
    "interview_prep": ["company_db", "calendar"],
    "calendar_query": ["calendar"],
    "weather_query": ["weather_api"],
    "resume": ["resume_engine"],
    "search": ["web_search"],
}


class IntentClassifier:
    """意图识别器：关键词优先，LLM 回退"""

    def __init__(self):
        pass

    def classify(self, text: str) -> IntentResult:
        """识别用户消息的意图"""
        # 1. 关键词匹配
        result = self._keyword_match(text)
        if result:
            return result

        # 2. 默认走通用对话 — 不再额外调 LLM 分类，避免多一次 API 往返
        #    LLM 只用于最终的回复生成，intent 靠关键词就够了
        return IntentResult(intent="chat", confidence=0.5, tools_needed=[])

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

