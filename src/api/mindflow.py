"""Mindflow API — 任务调度引擎接口.

将 mindflow 包接通到 Alpha-ID 服务，暴露三个端点：
  - GET  /api/v1/mindflow/status  — 引擎状态 + 已注册工具
  - POST /api/v1/mindflow/intent  — 文本意图识别
  - POST /api/v1/mindflow/execute — 执行任务指令

Gateway 通过 /v1/human/mindflow/* 代理到此路由。
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mindflow", tags=["Mindflow"])


# ── 请求/响应模型 ──


class IntentRequest(BaseModel):
    """意图识别请求"""
    text: str = Field(..., description="待识别的用户文本")


class ExecuteRequest(BaseModel):
    """任务执行请求 — 对应 mindflow.engine.TaskInstruction"""
    intent: str = Field("chat", description="意图名（如 route_plan / chat）")
    params: Dict[str, Any] = Field(default_factory=dict, description="任务参数")
    tools_needed: List[str] = Field(default_factory=list, description="显式指定工具列表（可选）")
    permission_level: str = Field("L1", description="权限等级 L1/L2/L3")
    user_id: str = Field("", description="发起用户 ID")
    raw_text: str = Field("", description="原始用户文本")


# ── 引擎单例 ──

_engine = None
_classifier = None


def _get_engine():
    """惰性初始化 MindflowEngine 单例"""
    global _engine
    if _engine is None:
        from mindflow import MindflowEngine
        _engine = MindflowEngine()
        logger.info("MindflowEngine 已初始化")
    return _engine


def _get_classifier():
    """惰性初始化 IntentClassifier 单例"""
    global _classifier
    if _classifier is None:
        try:
            from mindflow.intent import IntentClassifier
            _classifier = IntentClassifier()
            logger.info("IntentClassifier 已初始化")
        except Exception as e:
            logger.warning("IntentClassifier 初始化失败: %s", e)
    return _classifier


# ── 路由 ──


@router.get("/status")
def mindflow_status():
    """获取 Mindflow 引擎状态 + 已注册工具列表"""
    try:
        engine = _get_engine()
        return {
            "available": True,
            "tools": engine.tools.list_tools(),
            "permission_levels": ["L1", "L2", "L3"],
            "supported_intents": [
                "route_plan", "navigate_to", "interview_prep",
                "calendar_query", "weather_query", "resume",
                "search", "code_runner", "codex_agent",
                "ghost_identity", "chat",
            ],
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
            "tools": [],
        }


@router.post("/intent")
def mindflow_intent(req: IntentRequest):
    """识别用户文本意图（关键词优先 + LLM 回退）"""
    classifier = _get_classifier()
    if classifier is None:
        return {
            "available": False,
            "intent": "chat",
            "confidence": 0.0,
            "error": "IntentClassifier 不可用",
        }

    try:
        result = classifier.classify(req.text)
        return {
            "available": True,
            "text": req.text,
            "intent": result.intent,
            "confidence": result.confidence,
            "params": result.params,
            "tools_needed": result.tools_needed,
        }
    except Exception as e:
        return {
            "available": False,
            "text": req.text,
            "intent": "chat",
            "confidence": 0.0,
            "error": str(e),
        }


@router.post("/execute")
def mindflow_execute(req: ExecuteRequest):
    """执行任务指令 — 调用 MindflowEngine.execute"""
    try:
        from mindflow import TaskInstruction
        engine = _get_engine()

        instruction = TaskInstruction(
            task_id="",  # engine 内部会生成
            intent=req.intent,
            params=req.params,
            tools_needed=req.tools_needed,
            permission_level=req.permission_level,
            user_id=req.user_id,
            raw_text=req.raw_text,
        )

        result = engine.execute(instruction)

        # 序列化 ToolResult 字典
        results_serialized = {
            name: {
                "tool": tr.tool,
                "status": tr.status,
                "data": tr.data,
                "error": tr.error,
                "duration_ms": tr.duration_ms,
            }
            for name, tr in result.results.items()
        }

        return {
            "success": result.status == "success",
            "task_id": result.task_id,
            "status": result.status,
            "summary": result.summary,
            "results": results_serialized,
            "needs_confirmation": result.needs_confirmation,
            "error": result.error,
        }
    except Exception as e:
        logger.error("mindflow/execute 失败: %s", e, exc_info=True)
        return {
            "success": False,
            "status": "error",
            "error": str(e),
        }
