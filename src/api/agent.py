"""Agent SDK API 路由 — 接通 AgentLoop"""

from fastapi import APIRouter, Depends

from auth.middleware import require_user
from core.agent import AgentLoop

router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])


@router.post("/chat")
def agent_chat(body: dict, alpha_id: str = Depends(require_user)):
    """Agent 对话入口"""
    message = body.get("message", "")
    if not message:
        return {"success": False, "error": "message 必填"}

    loop = AgentLoop(alpha_id=alpha_id)
    reply = loop.run(message)
    return {"success": True, "data": {"reply": reply}}
