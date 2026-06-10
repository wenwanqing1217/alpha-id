# -*- coding: utf-8 -*-
"""
ReAct 思考引擎 — 结构化思考 + 工具调用循环

与 AgentLoop 的关系：
  AgentLoop = 通用的 LLM+Tools+Loop（聊天/问答）
  ReActEngine = 专用的 think() 引擎（主动思考/规划/决策）

用法：
    engine = ReActEngine(alpha_id="Alpha-001", brain=twin_brain)
    result = engine.think("检查一下我的状态")
    # -> {"thought": "...", "action": "...", "observation": "...", "status": "ok"}
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from core.agent import Tool, _call_llm, _parse_tool_call

# ── 思考系统提示 ──

THINK_SYSTEM_PROMPT = """你是一个 AI Agent 的「思考模块」，负责主动思考、规划和决策。

## 你的身份
- Alpha-ID: {alpha_id}
- 你是一个数字身份的思考层，不是聊天助手

## 你的思考模式
每次思考请按以下格式回复：

思考：<你的分析>
__TOOL_CALL__ 工具名称({{＂参数名＂: ＂参数值＂}})

或：
思考：<你的分析>
最终：<你的结论/回答>

## 可用的工具
{tools_schemas}

## 思考原则
1. 先分析当前状态，再决定行动
2. 一次只做一个行动
3. 行动完成后观察结果，再决定下一步
4. 如果不需要任何行动，直接输出「最终」"""


class ReActEngine:
    """ReAct 思考引擎"""

    def __init__(
        self,
        alpha_id: str,
        brain=None,
        llm_api_key: str = "",
        llm_base_url: str = "",
        model: str = "",
    ):
        self.alpha_id = alpha_id
        self.brain = brain  # Optional[TwinBrain]
        self.api_key = llm_api_key or os.environ.get("LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = llm_base_url or os.environ.get("LLM_BASE_URL", "")
        self.model = model or os.environ.get("LLM_MODEL", "deepseek-v4-flash")
        self.max_turns = int(os.environ.get("REACT_MAX_TURNS", "5"))
        self.tools: List[Tool] = []
        self._register_tools()

    def _register_tools(self):
        """注册思考可用的工具"""

        tools = []

        # 1. search_memory — 搜索记忆
        tools.append(
            Tool(
                name="search_memory",
                description="搜索相关的长期记忆",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "搜索关键词"}},
                    "required": ["query"],
                },
                fn=lambda query: self._search_memory(query),
            )
        )

        # 2. query_profile — 查询身份
        tools.append(
            Tool(
                name="query_profile",
                description="查询自己的身份档案信息",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                fn=lambda: self._query_profile(),
            )
        )

        # 3. get_time — 获取当前时间
        tools.append(
            Tool(
                name="get_time",
                description="获取当前的日期和时间",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                fn=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        )

        # 4. evaluate_risk — 风险评估
        tools.append(
            Tool(
                name="evaluate_risk",
                description="评估某个行动的风险等级",
                parameters={
                    "type": "object",
                    "properties": {
                        "action_desc": {
                            "type": "string",
                            "description": "要评估的行动描述",
                        }
                    },
                    "required": ["action_desc"],
                },
                fn=lambda action_desc: self._evaluate_risk(action_desc),
            )
        )

        # 5. get_status — 获取大脑状态
        tools.append(
            Tool(
                name="get_status",
                description="获取当前大脑状态信息（消息数、待办请求、信誉分）",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                fn=self._get_status,
            )
        )

        # 6. save_insight — 保存洞察到长期记忆
        tools.append(
            Tool(
                name="save_insight",
                description="将重要的思考结果保存到长期记忆中",
                parameters={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "要保存的洞察内容",
                        },
                        "importance": {
                            "type": "string",
                            "description": "重要性: low/medium/high",
                            "enum": ["low", "medium", "high"],
                        },
                    },
                    "required": ["content"],
                },
                fn=lambda content, importance="medium": self._save_insight(content, importance),
            )
        )

        self.tools = tools

    # ── 工具实现 ──

    def _search_memory(self, query: str) -> str:
        if self.brain and self.brain._memory:
            results = self.brain.memory.query(query_text=query, limit=5)
            if results:
                return json.dumps(results, ensure_ascii=False, default=str)
            return "没有找到相关记忆"
        return "记忆系统未就绪"

    def _query_profile(self) -> str:
        try:
            from alpha_id.container import Container

            container = Container.instance()
            profile = container.identity.get_user_profile(self.alpha_id)
            if profile:
                return json.dumps(profile, ensure_ascii=False, default=str)
        except Exception:
            pass
        return f"Alpha-ID: {self.alpha_id}（无详细信息）"

    def _evaluate_risk(self, action_desc: str) -> str:
        try:
            from core.risk_engine import RiskAssessmentEngine

            RiskAssessmentEngine()
            # 简单检查关键词
            risky_keywords = ["删除", "修改", "发送", "共享", "公开", "delete", "modify", "share"]
            score = 0.0
            for kw in risky_keywords:
                if kw in action_desc:
                    score += 0.35
            score = min(score, 1.0)
            level = "low" if score < 0.4 else "medium" if score < 0.7 else "high"
            return json.dumps(
                {
                    "risk_score": round(score, 2),
                    "risk_level": level,
                    "advice": "建议继续" if level == "low" else "需要谨慎" if level == "medium" else "建议暂缓",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return f"风险评估失败: {e}"

    def _get_status(self) -> str:
        status = {}
        if self.brain:
            status["state"] = self.brain.state.value if hasattr(self.brain.state, "value") else str(self.brain.state)
            status["message_count"] = self.brain._message_count
            try:
                status["reputation"] = self.brain.compute_reputation()
            except Exception:
                pass
            if self.brain._social:
                try:
                    requests = self.brain.social.get_pending_friend_requests(self.alpha_id)
                    status["pending_friend_requests"] = len(requests)
                except Exception:
                    pass
        return json.dumps(status, ensure_ascii=False, default=str)

    def _save_insight(self, content: str, importance: str = "medium") -> str:
        sensitivity_map = {"low": 10, "medium": 30, "high": 60}
        if self.brain and self.brain._memory:
            self.brain.memory.save(
                content=content,
                tags=["insight", importance],
                sensitivity=sensitivity_map.get(importance, 30),
            )
            return "洞察已保存"
        return "记忆系统未就绪，洞察未保存"

    # ── 核心思考循环 ──

    def think(self, context: str = "") -> Dict[str, Any]:
        """执行一次主动思考循环

        Args:
            context: 额外的上下文提示

        Returns:
            Dict 包含思考结果
        """
        if not self.api_key:
            return {
                "status": "error",
                "thought": "",
                "action": "",
                "observation": "LLM 未配置：请设置 LLM_API_KEY 或 OPENAI_API_KEY",
                "tool_calls": 0,
            }

        # 1. 构建提示
        tool_schemas = json.dumps(
            [t.to_schema() for t in self.tools],
            ensure_ascii=False,
            indent=2,
        )
        system = THINK_SYSTEM_PROMPT.format(
            alpha_id=self.alpha_id,
            tools_schemas=tool_schemas,
        )

        user_prompt = "请进行一次主动思考。"
        if context:
            user_prompt += f"\n\n额外上下文：\n{context}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]

        tool_calls = 0
        observations = []

        for turn in range(self.max_turns):
            # 2. 调用 LLM
            # Set env vars for _call_llm to pick up
            if self.api_key:
                os.environ["OPENAI_API_KEY"] = self.api_key
            if self.base_url:
                os.environ["OPENAI_BASE_URL"] = self.base_url
            reply = _call_llm(
                messages,
                [t.to_schema() for t in self.tools],
                self.model,
            )

            # 3. 解析 ReAct 格式
            tool_call = _parse_tool_call(reply)

            if tool_call is None:
                # 最终回答
                return {
                    "status": "ok",
                    "thought": reply,
                    "action": "final_answer",
                    "observation": observations[-1] if observations else "",
                    "tool_calls": tool_calls,
                }

            # 4. 执行工具
            _, name, args = tool_call
            tool_calls += 1
            tool = {t.name: t for t in self.tools}.get(name)
            if tool is None:
                result = f"[未知工具: {name}]"
            else:
                try:
                    result = tool(**args)
                except Exception as e:
                    result = f"[工具执行错误] {e}"

            observations.append(result)

            # 5. 追加到消息（用 user role 避免 DeepSeek 要求 tool_call_id）
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": f"[工具 {name} 执行结果]\n{result}"})

        # 超时
        return {
            "status": "ok",
            "thought": f"[达到最大轮次 {self.max_turns}] " + (observations[-1] if observations else ""),
            "action": "max_turns_reached",
            "observation": observations[-1] if observations else "",
            "tool_calls": tool_calls,
        }
