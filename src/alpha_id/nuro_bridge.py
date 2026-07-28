"""
Alpha-ID NURO Bridge — 桌宠连接
=================================

打通 NURO 桌面宠物与 Alpha-ID：
  - NURO 用本地小模型（MiniCPM-o-4.5）做轻量推理
  - 需要深度推理时，调用 Alpha-ID 的智能脑
  - NURO 观察到用户行为 → 传给 Smart Capture
  - Alpha-ID 的反馈 → NURO 展示给用户

设计原则：
  - NURO 是"眼睛和嘴巴"：观察用户、跟用户聊天
  - Alpha-ID 是"大脑"：深度思考、长期记忆、决策支持
  - 简单问题 NURO 本地回答，复杂问题交给云端 LLM
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class NUROEvent:
    """NURO 事件"""
    type: str = ""            # user_activity / screen_observed / reminder / greeting
    content: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class NUROBridge:
    """
    NURO 桥接器

    用法：
        nuro = NUROBridge(fairy_brain, alpha_id_agent)
        nuro.on_user_activity(handle_activity)
        nuro.reminder("你该休息了")
    """

    def __init__(self, fairy_brain=None, alpha_id_agent=None, memory_store=None):
        self._fairy = fairy_brain          # FairyBrain (本地小模型)
        self._alphaid = alpha_id_agent     # Alpha-ID Agent
        self._memory = memory_store        # MemoryStore
        self._callbacks: List[Callable[[NUROEvent], None]] = []
        self._stats = {"local_replies": 0, "cloud_replies": 0, "observations": 0}

    def on_event(self, callback: Callable[[NUROEvent], None]):
        """注册事件回调"""
        self._callbacks.append(callback)

    # ── NURO ↔ Alpha-ID ──

    def chat(self, user_input: str, use_local: bool = True) -> str:
        """
        NURO 聊天入口

        策略：
        - 简单问题 → 本地小模型（快、免费、隐私）
        - 复杂问题 → Alpha-ID 智能脑（需要记忆和推理）
        """
        if not user_input:
            return ""

        # 判断复杂度
        if use_local and self._is_simple(user_input) and self._fairy and self._fairy.available:
            return self._local_chat(user_input)
        else:
            return self._cloud_chat(user_input)

    def _is_simple(self, text: str) -> bool:
        """判断问题是否简单（本地小模型能处理）"""
        # 短问题、闲聊 → 简单
        if len(text) < 50:
            return True

        # 需要记忆或深度推理的 → 复杂
        complex_keywords = ["为什么", "怎么", "帮我", "分析", "比较", "决定",
                            "计划", "总结", "之前", "上次", "记忆"]
        complex_count = sum(1 for kw in complex_keywords if kw in text)
        if complex_count >= 2:
            return False

        return True

    def _local_chat(self, user_input: str) -> str:
        """本地小模型回复"""
        if not self._fairy:
            return self._cloud_chat(user_input)

        try:
            # 注入用户上下文到系统提示
            context = self._get_user_context_summary()
            if context:
                self._fairy.system_prompt += f"\n\n[用户上下文]\n{context}"

            reply = self._fairy.generate(user_input, max_tokens=300)
            self._stats["local_replies"] += 1
            return reply
        except Exception as e:
            logger.debug("Local chat failed: %s", e)
            return self._cloud_chat(user_input)

    def _cloud_chat(self, user_input: str) -> str:
        """云端 LLM 回复（Alpha-ID）"""
        if not self._alphaid:
            return "我现在无法连接，稍后再试。"

        try:
            # 通过 TwinBrain 聊天
            result = self._alphaid.think(user_input)
            reply = result.get("response", "")
            if isinstance(reply, dict):
                reply = reply.get("message", reply.get("text", ""))
            self._stats["cloud_replies"] += 1
            return str(reply) if reply else "我在思考中..."
        except Exception as e:
            logger.error("Cloud chat failed: %s", e)
            return "我遇到了一点问题，稍后再试。"

    def _get_user_context_summary(self) -> str:
        """获取用户上下文摘要（给本地模型用）"""
        if not self._memory:
            return ""

        try:
            # 获取最近的记忆
            recent = self._memory.search(query="项目 目标 偏好", limit=5)
            if not recent:
                return ""

            parts = []
            for mem in recent[:3]:
                content = mem.get("content", "")
                if content:
                    parts.append(f"- {content[:100]}")

            return "\n".join(parts)
        except Exception:
            return ""

    # ── 观察与反馈 ──

    def observe(self, observation_type: str, content: str, metadata: Dict = None):
        """
        NURO 观察到用户行为

        Args:
            observation_type: user_activity / screen_observed / idle
            content: 观察内容
            metadata: 附加信息
        """
        event = NUROEvent(
            type=observation_type,
            content=content,
            metadata=metadata or {},
        )

        self._stats["observations"] += 1

        # 传给 Smart Capture 分析
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def reminder(self, message: str):
        """NURO 提醒用户"""
        event = NUROEvent(
            type="reminder",
            content=message,
        )

        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    # ── 主动服务 ──

    def proactive_check(self) -> Optional[str]:
        """
        NURO 主动检查用户状态

        定时调用：
        - 用户是否很久没休息了？
        - 之前说要做的事完成了吗？
        - 有没有值得提醒的？
        """
        if not self._memory:
            return None

        try:
            # 检查最近有没有拖延的事
            pending = self._memory.search(query="要做 计划 目标 截止", limit=5)
            if pending:
                # 简单提醒
                for mem in pending:
                    content = mem.get("content", "")
                    if "截止" in content or "DDL" in content:
                        return f"提醒：{content[:100]}"

            return None
        except Exception:
            return None

    # ── 屏幕观察 ──

    def observe_screen(self, image_path: str) -> str:
        """
        NURO 看屏幕

        用本地多模态模型分析屏幕内容
        """
        if not self._fairy or not self._fairy.available:
            return ""

        try:
            description = self._fairy.describe_image(
                image_path,
                prompt="用户在做什么？简要描述屏幕内容。"
            )
            self.observe("screen_observed", description, {"image": image_path})
            return description
        except Exception as e:
            logger.debug("Screen observation failed: %s", e)
            return ""

    def get_stats(self) -> Dict[str, int]:
        return self._stats.copy()
