"""Agent 调度端点 — 总助通过 AgentGraph 调度任务闭环

TERM: AgentGraph — 通过 findskill 找最优工具路径

这是"总助接入 AgentGraph"的核心端点：
  1. 接收意图（skill_name + params）
  2. 查 AgentGraph findskill 找最优 agent
  3. 调用该 agent 的 HTTP 端点
  4. 记录调用边（success/latency）→ 反哺 AgentGraph 统计
  5. 返回结果

调用方式：
  POST /api/v1/agent/dispatch
  {
    "skill": "video_generate",
    "params": {"subject": "香薰种草"},
    "prefer": "free",
    "caller": "feishu_assistant"
  }

这样飞书总助、DS 看板、NURO 桌宠都能通过这个端点调度任何已注册的 agent。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent-dispatch"])


class DispatchRequest(BaseModel):
    """调度请求"""
    skill: str                    # 要调用的 skill（如 video_generate / channel_copy）
    params: Dict[str, Any] = {}   # 调用参数
    prefer: str = "free"          # 选路策略：free / fast / reliable / any
    caller: str = "unknown"       # 调用方标识（如 feishu_assistant / ds_dashboard / nuro）


@router.post("/dispatch")
async def dispatch(req: Request):
    """调度任务到最优 agent

    流程：
      1. AgentGraph.find_best_agent(skill, prefer) 找最优 agent
      2. 通过 HTTP 调用该 agent 的端点
      3. 记录调用边（success/latency）反哺 AgentGraph
      4. 发布成长事件（如果成功）
    """
    try:
        body = await req.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "body required"})

    skill = body.get("skill", "")
    params = body.get("params", {})
    prefer = body.get("prefer", "free")
    caller = body.get("caller", "unknown")

    if not skill:
        return JSONResponse(status_code=400, content={"error": "skill 必填"})

    # ── 1. findskill ──
    try:
        from core.agent_graph import get_agent_graph
        graph = get_agent_graph()
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"error": f"AgentGraph 不可用: {e}"},
        )

    best = graph.find_best_agent(skill, prefer=prefer)
    if not best:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": f"没有找到提供 skill '{skill}' 的 agent",
                "skill": skill,
                "available_skills": graph.list_skills(),
            },
        )

    # ── 2. 调用 agent ──
    start = time.perf_counter()
    success = False
    result_data: Dict[str, Any] = {}

    try:
        # 根据 agent_type 决定调用方式
        if best.agent_type == "core" and best.agent_id == "core:alpha-id":
            # 内部 Alpha-ID agent，直接本地调用（不走 HTTP）
            result_data = await _call_internal_alpha_id(skill, params)
        elif best.agent_type == "tool" and best.agent_id == "tool:ds-copy":
            # DS 文案 agent
            result_data = await _call_ds_copy(best.endpoint, skill, params)
        elif best.agent_type == "tool" and best.agent_id == "tool:moneyprinter":
            # MoneyPrinterTurbo 视频生成
            result_data = await _call_moneyprinter(best.endpoint, skill, params)
        elif best.agent_type == "feed":
            # 资讯类 agent
            result_data = await _call_feed(best.endpoint, skill, params)
        else:
            # 外部 agent（用户 DIY），通过 A2A /call 调用
            result_data = await _call_external_agent(best.endpoint, best.agent_id, skill, params)

        success = result_data.get("success", True)

    except Exception as e:
        logger.error("Agent 调用失败: %s", e, exc_info=True)
        result_data = {"success": False, "error": str(e)}

    latency_ms = (time.perf_counter() - start) * 1000

    # ── 3. 记录调用边（反哺 AgentGraph）──
    graph.record_call(
        caller=caller,
        target=best.agent_id,
        skill=skill,
        success=success,
        latency_ms=latency_ms,
    )

    # ── 4. 发布成长事件（如果成功）──
    if success:
        try:
            from core.event_bus import get_event_bus
            bus = get_event_bus()
            if bus:
                bus.emit("growth.event", {
                    "alpha_id": body.get("alpha_id", caller),
                    "tool": skill,
                    "success": True,
                    "description": f"AgentGraph 调度: {skill}",
                    "source": caller,
                })
        except Exception:
            pass

    return {
        "success": success,
        "skill": skill,
        "agent": {
            "agent_id": best.agent_id,
            "name": best.name,
            "type": best.agent_type,
            "is_free": best.is_free,
        },
        "latency_ms": round(latency_ms, 1),
        "result": result_data,
    }


@router.get("/skills")
async def list_all_skills():
    """列出所有可用的 skill 及其提供者"""
    try:
        from core.agent_graph import get_agent_graph
        graph = get_agent_graph()
        return {
            "success": True,
            "skills": graph.list_skills(),
            "agents": [
                {
                    "agent_id": n.agent_id,
                    "name": n.name,
                    "type": n.agent_type,
                    "is_free": n.is_free,
                    "is_online": n.is_online,
                    "skills": n.skills,
                    "description": n.description,
                }
                for n in graph.list_agents()
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 内部调用实现 ──────────────────────────────────────────────


async def _call_internal_alpha_id(skill: str, params: Dict) -> Dict:
    """调用 Alpha-ID 内部能力"""
    if skill == "chat":
        # 走 TwinBrain 闲聊
        return {"success": True, "reply": "(内部闲聊暂未接入 dispatch)"}
    elif skill == "growth_stats":
        from alpha_id.growth_tracker import STAGES, GrowthTracker
        tracker = GrowthTracker()
        return {
            "success": True,
            "stages": STAGES,
            "stage_info": tracker.get_stage_info(params.get("total_exp", 0)),
        }
    return {"success": False, "error": f"未知内部 skill: {skill}"}


async def _call_ds_copy(ds_url: str, skill: str, params: Dict) -> Dict:
    """调用 DS 文案 agent"""
    import httpx
    product = params.get("product") or params.get("subject") or params.get("text", "")
    if not product:
        return {"success": False, "error": "缺少商品名"}

    import asyncio
    async with httpx.AsyncClient(timeout=30) as client:
        tasks = [
            client.post(
                f"{ds_url.rstrip('/')}/api/ai/channel-copy",
                json={
                    "platform": platform,
                    "product": product,
                    "description": params.get("description", ""),
                    "price": params.get("price", ""),
                    "condition": params.get("condition", "全新未拆"),
                    "tone": "casual",
                },
            )
            for platform in ("xianyu", "xiaohongshu")
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    sections = []
    names = {"xianyu": "🐟 闲鱼", "xiaohongshu": "📕 小红书"}
    for platform, resp in zip(("xianyu", "xiaohongshu"), responses):
        name = names[platform]
        if isinstance(resp, Exception):
            sections.append(f"{name}\n❌ 生成失败：{resp}")
            continue
        try:
            data = resp.json()
            if not resp.is_success:
                sections.append(f"{name}\n❌ {data.get('error', '未知错误')}")
                continue
            r = data.get("result", {})
            sections.append(
                f"{name}\n【标题】{r.get('title', '')}\n"
                f"【正文】\n{r.get('body', '')}\n"
                f"【标签】{' '.join(r.get('tags', []))}"
            )
        except Exception as e:
            sections.append(f"{name}\n❌ 解析失败：{e}")

    return {"success": True, "reply": "\n\n──────────\n\n".join(sections)}


async def _call_moneyprinter(mp_url: str, skill: str, params: Dict) -> Dict:
    """调用 MoneyPrinterTurbo 视频生成"""
    import httpx
    subject = params.get("subject") or params.get("title") or params.get("text", "")
    if not subject:
        return {"success": False, "error": "缺少视频主题"}

    if skill == "video_generate":
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{mp_url.rstrip('/')}/api/v1/videos",
                json={
                    "video_subject": subject,
                    "video_aspect": params.get("aspect", "9:16"),
                    "video_language": params.get("language", "zh"),
                    "video_concat_mode": "random",
                    "paragraph_number": 2,
                    "n_threads": 2,
                },
            )
            data = resp.json()
            task_id = data.get("task_id") or data.get("data", {}).get("task_id")
            return {"success": bool(task_id), "task_id": task_id, "subject": subject}

    elif skill == "video_status":
        task_id = params.get("task_id", "")
        if not task_id:
            return {"success": False, "error": "缺少 task_id"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{mp_url.rstrip('/')}/api/v1/tasks/{task_id}")
            data = resp.json()
            return {"success": True, "task": data}

    return {"success": False, "error": f"未知 video skill: {skill}"}


async def _call_feed(alpha_id_url: str, skill: str, params: Dict) -> Dict:
    """调用资讯类 agent（GitHub/HN/ArXiv）"""
    try:
        from alpha_id.feed import AgentFeed
        feed = AgentFeed()
        items = feed.fetch_latest()
        limit = int(params.get("limit", 10))
        return {
            "success": True,
            "items": [
                {
                    "title": item.title,
                    "summary": item.summary[:200],
                    "url": item.url,
                    "source": item.source,
                    "tags": item.tags,
                }
                for item in items[:limit]
            ],
            "total": len(items),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _call_external_agent(
    endpoint: str, agent_id: str, skill: str, params: Dict
) -> Dict:
    """调用外部 agent（用户 DIY，通过 HTTP）

    外部 agent 需实现 POST /a2a/call 端点，接收：
      { "skill": "...", "params": {...} }
    返回：
      { "success": true, "result": {...} }
    """
    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{endpoint.rstrip('/')}/a2a/call",
            json={"skill": skill, "params": params},
        )
        return resp.json()
