"""Agent SDK API 路由 — AgentLoop + TwinBrain + ReActEngine 接通

提供 /api/v1/agent/chat 端点，将核心 AI 能力暴露为 HTTP API。
支持标准 AgentLoop 对话和 ReAct 思考引擎两种模式。

依赖注入迁移（Phase 2）：
- 所有路由通过 Depends(get_container) 获取 Container
- _get_brain 改为依赖注入友好的形式
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from alpha_id.container import Container, get_container
from auth.middleware import require_user
from core.agent import AgentLoop
from core.twin_brain import TwinBrain

router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])


# ── 请求/响应模型 ──


class ChatRequest(BaseModel):
    """对话请求"""

    message: str = Field(..., min_length=1, max_length=4096, description="用户消息")
    use_react: bool = Field(default=False, description="是否使用 ReAct 思考引擎")


class ChatResponse(BaseModel):
    """对话响应"""

    alpha_id: str
    reply: str
    brain_state: str = "idle"


class BrainStatusResponse(BaseModel):
    """大脑状态响应"""

    alpha_id: str
    state: str
    settings: dict


# ── 端点 ──


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest,
         alpha_id: str = Depends(require_user),
         container: Container = Depends(get_container)):
    """与 Agent 对话 — 自动选择 AgentLoop 或 ReActEngine"""
    brain = TwinBrain(alpha_id=alpha_id, storage=container.storage)

    if body.use_react:
        # 使用 ReAct 思考引擎
        from core.agent_react import ReActEngine

        engine = ReActEngine(alpha_id=alpha_id, brain=brain)
        result = engine.think(body.message)
        reply = result.get("thought", "") or result.get("observation", "")
    else:
        # 使用标准 AgentLoop
        loop = AgentLoop(alpha_id=alpha_id)
        reply = loop.run(body.message)

    return ChatResponse(
        alpha_id=alpha_id,
        reply=reply,
        brain_state=brain.state.value if brain.state else "idle",
    )


@router.get("/status", response_model=BrainStatusResponse)
def status(alpha_id: str = Depends(require_user),
           container: Container = Depends(get_container)):
    """查询大脑状态"""
    brain = TwinBrain(alpha_id=alpha_id, storage=container.storage)
    return BrainStatusResponse(
        alpha_id=alpha_id,
        state=brain.state.value if brain.state else "sleep",
        settings={},
    )
