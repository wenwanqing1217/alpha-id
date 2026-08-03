"""A2A Protocol API 路由

将 a2a.py 的 A2AServer 端点重构为 APIRouter，
使其成为 main.py 路由系统的一等公民：
  - 享受 JWT auth、RateLimit、CSRF、CORS 中间件
  - 通过 Container DI 获取存储和身份
  - 审计日志接入 observability 指标
  - 调用结果自动回写双链记忆

Protocol:
  POST /api/v1/a2a/call        — Agent 调用
  POST /api/v1/a2a/register    — Agent 注册
  GET  /api/v1/a2a/discover     — 发现 Agent
  GET  /api/v1/a2a/agents       — 列出所有 Agent
  GET  /api/v1/a2a/skills       — 列出可用技能
  GET  /api/v1/a2a/audit        — 审计日志查询
  GET  /api/v1/a2a/health       — 健康检查
"""

import json
import logging
import time
import uuid
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from alpha_id.container import Container, get_container
from auth.middleware import require_user
from core.a2a import (
    A2AAgentInfo,
    A2AAuditFilter,
    A2AAuditLog,
    A2ACallRequest,
    A2ACallResponse,
    A2ARegisterRequest,
    A2ARegisterResponse,
    A2ADiscoverResponse,
    A2APermissionDenied,
    A2ARegistry,
    A2ASkillRegistry,
)
from core.observability import record_http_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/a2a", tags=["A2A 协议"])


# ── Pydantic 请求/响应模型 ──


class A2ACallBody(BaseModel):
    """A2A 调用请求体"""
    caller: str = Field("", description="调用方 Agent ID")
    target: str = Field("", description="目标 Agent ID")
    skill: str = Field("", description="要调用的技能名")
    params: Dict[str, Any] = Field(default_factory=dict, description="技能参数")
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = Field(default_factory=time.time)
    proof: str = Field("", description="Ed25519 签名 (hex)")


class A2ARegisterBody(BaseModel):
    """Agent 注册请求体"""
    agent_id: str = Field("", description="Agent ID")
    did: str = Field("", description="DID")
    endpoint: str = Field("", description="Agent 端点地址")
    public_key_hex: str = Field("", description="公钥 hex")
    skill_list: List[str] = Field(default_factory=list, description="技能列表")
    permission_scope: List[str] = Field(default_factory=list)
    call_constraint: Dict[str, Any] = Field(default_factory=dict)
    memory_policy: str = Field("write_summary")


class A2AAuditQuery(BaseModel):
    """审计日志查询（支持持久化存储筛选 + 分页）"""
    caller_agent_id: str = Field("", description="按调用方过滤")
    target_agent_id: str = Field("", description="按目标过滤")
    skill: str = Field("", description="按技能名过滤")
    start_time: str = Field("", description="起始时间 (ISO 格式)")
    end_time: str = Field("", description="结束时间 (ISO 格式)")
    limit: int = Field(100, ge=1, le=1000, description="每页条数")
    offset: int = Field(0, ge=0, description="偏移量")


class A2ACapability(BaseModel):
    """Agent 能力声明（Google A2A 兼容）"""
    streaming: bool = False
    push_notifications: bool = False
    state_transition_history: bool = False


class A2AAuthentication(BaseModel):
    """Agent 认证配置（Google A2A 兼容）"""
    schemes: List[str] = Field(default_factory=lambda: ["bearer"])
    credentials: Optional[str] = None


class A2AAgentCard(BaseModel):
    """Agent Card（Google A2A 规范：/.well-known/agent.json）

    参考: https://a2a-protocol.org/specification/
    """
    name: str = Field(..., description="Agent 名称")
    description: str = Field("", description="Agent 描述")
    url: str = Field(..., description="Agent 端点 URL")
    version: str = Field("1.0.0", description="版本号")
    capabilities: A2ACapability = Field(default_factory=A2ACapability)
    authentication: A2AAuthentication = Field(default_factory=A2AAuthentication)
    skills: List[Dict[str, Any]] = Field(default_factory=list, description="可用技能列表")
    default_input_modes: List[str] = Field(default_factory=lambda: ["text"])
    default_output_modes: List[str] = Field(default_factory=lambda: ["text"])


# ── 全局状态（服务级单例，与 main.py lifespan 生命周期一致）──


# 技能注册表、注册中心、审计日志在模块级别创建，
# 通过 lifespan 初始化和关闭（见 main.py 的 a2a_server 生命周期管理）
# 此处先用空对象占位，由 main.py lifespan 通过 app.state 注入

def _get_a2a_state(request: Request) -> dict:
    """从 app.state 获取 A2A 运行时状态"""
    state = getattr(request.app.state, "a2a_state", None)
    if state is None:
        raise HTTPException(status_code=503, detail="A2A 服务未初始化")
    return state


def _get_skills(state: dict) -> A2ASkillRegistry:
    return state["skills"]


def _get_registry(state: dict) -> A2ARegistry:
    return state["registry"]


def _get_audit(state: dict) -> A2AAuditLog:
    return state["audit"]


def _get_signer(state: dict):
    return state.get("signer")


# ── 端点实现 ──


@router.post("/call")
async def a2a_call(
    body: A2ACallBody,
    request: Request,
    container: Container = Depends(get_container),
):
    """A2A 调用 — 重放防护 + Ed25519 签名验证 + 权限授权 + 技能执行 + 审计

    6 步最小链的关键一步：A2A 调用结果会自动回写双链记忆。
    """
    start_time = time.perf_counter()
    state = _get_a2a_state(request)
    skills = _get_skills(state)
    registry = _get_registry(state)
    audit = _get_audit(state)
    signer = _get_signer(state)
    did = state.get("did", "")

    # 构建内部请求对象
    call_req = A2ACallRequest(
        caller=body.caller,
        target=body.target,
        skill=body.skill,
        params=body.params,
        request_id=body.request_id,
        timestamp=body.timestamp,
        proof=body.proof,
    )

    # ── 重放防护 (set + deque: O(1) 查找 + O(1) 自动淘汰) ──
    if abs(time.time() - call_req.timestamp) > 300:
        record_http_request(request.method, "a2a/call", 401, time.perf_counter() - start_time)
        return JSONResponse(
            A2ACallResponse(
                success=False,
                error="请求已过期 (重放攻击?)",
                request_id=call_req.request_id,
            ).to_dict(),
            status_code=401,
        )

    seen_set = state.setdefault("seen_requests_set", set())
    seen_deque = state.setdefault("seen_requests_deque", deque(maxlen=10000))
    replay_key = (call_req.caller, call_req.request_id)
    if replay_key in seen_set:
        record_http_request(request.method, "a2a/call", 401, time.perf_counter() - start_time)
        return JSONResponse(
            A2ACallResponse(
                success=False,
                error="重复请求 (重放)",
                request_id=call_req.request_id,
            ).to_dict(),
            status_code=401,
        )
    seen_set.add(replay_key)
    seen_deque.append(replay_key)

    # ── Ed25519 签名验证 ──
    # 关键安全修复：必须用调用方的公钥验证，而非服务器的公钥
    if call_req.proof:
        verified = False
        caller_pubkey = ""

        # 优先：从注册表获取调用方的公钥
        try:
            caller_agent = registry.get_agent(call_req.caller)
            caller_pubkey = caller_agent.get("public_key_hex", "")
        except HTTPException:
            pass  # 未注册的调用方，尝试回退

        if caller_pubkey:
            # 用调用方的公钥验证签名（正确做法）
            try:
                from nacl.signing import VerifyKey
                verify_key = VerifyKey(bytes.fromhex(caller_pubkey))
                verify_key.verify(call_req.signable_bytes(), bytes.fromhex(call_req.proof))
                verified = True
            except Exception:
                verified = False
        elif signer:
            # 回退：用服务器签名器验证（仅当调用方未注册时）
            # 这允许未注册的 Agent 在签名已知的情况下调用，但不建立身份绑定
            verified = signer.verify(call_req.signable_bytes(), call_req.proof)

        if not verified:
            record_http_request(request.method, "a2a/call", 401, time.perf_counter() - start_time)
            return JSONResponse(
                A2ACallResponse(
                    success=False,
                    error="签名验证失败",
                    request_id=call_req.request_id,
                ).to_dict(),
                status_code=401,
            )

    # ── 权限授权 ──
    try:
        registry.authorize_call(
            caller=call_req.caller,
            target=call_req.target,
            skill=call_req.skill,
        )
    except A2APermissionDenied as exc:
        audit.record(
            event="permission_denied",
            caller_agent_id=call_req.caller,
            target_agent_id=call_req.target,
            skill=call_req.skill,
            request_id=call_req.request_id,
            error=str(exc),
        )
        record_http_request(request.method, "a2a/call", 403, time.perf_counter() - start_time)
        return JSONResponse(
            A2ACallResponse(
                success=False,
                error=str(exc),
                request_id=call_req.request_id,
            ).to_dict(),
            status_code=403,
        )

    # ── 技能执行 ──
    try:
        result = await skills.execute_async(call_req.skill, call_req.params)
        elapsed = (time.perf_counter() - start_time) * 1000

        # 生成执行证明
        proof = ""
        if signer:
            proof_data = json.dumps({"request_id": call_req.request_id, "result": str(result)}, sort_keys=True)
            proof = signer.sign(proof_data.encode())

        # 审计记录
        audit.record(
            event="call_completed",
            caller_agent_id=call_req.caller,
            target_agent_id=call_req.target,
            skill=call_req.skill,
            request_id=call_req.request_id,
            success=True,
        )
        registry.record_agent_call(did, success=True)

        # ── 回写双链记忆（使用缓存的管理器，避免每次调用都 PBKDF2） ──
        dual_chain_cache = state.get("dual_chain_cache", {})
        _write_a2a_memory(
            container=container,
            alpha_id=call_req.caller or did,
            call_req=call_req,
            result=result,
            success=True,
            elapsed_ms=elapsed,
            dual_chain_cache=dual_chain_cache,
        )

        # 记录 HTTP 请求指标
        duration = time.perf_counter() - start_time
        record_http_request(
            method=request.method,
            endpoint="a2a/call",
            status=200,
            duration=duration,
        )

        return A2ACallResponse(
            success=True,
            result=result,
            request_id=call_req.request_id,
            executor=did,
            proof=proof,
            execution_time_ms=elapsed,
        ).to_dict()

    except Exception as e:
        elapsed = (time.perf_counter() - start_time) * 1000
        audit.record(
            event="call_completed",
            caller_agent_id=call_req.caller,
            target_agent_id=call_req.target,
            skill=call_req.skill,
            request_id=call_req.request_id,
            success=False,
            error=str(e),
        )
        registry.record_agent_call(did, success=False)

        # 失败也回写记忆
        dual_chain_cache = state.get("dual_chain_cache", {})
        _write_a2a_memory(
            container=container,
            alpha_id=call_req.caller or did,
            call_req=call_req,
            result=None,
            success=False,
            elapsed_ms=elapsed,
            error=str(e),
            dual_chain_cache=dual_chain_cache,
        )

        record_http_request(request.method, "a2a/call", 500, time.perf_counter() - start_time)

        return JSONResponse(
            A2ACallResponse(
                success=False,
                error=str(e),
                request_id=call_req.request_id,
                executor=did,
                execution_time_ms=elapsed,
            ).to_dict(),
            status_code=500,
        )


@router.post("/register")
async def a2a_register(
    body: A2ARegisterBody,
    request: Request,
):
    """Agent 注册 — 将远程 Agent 加入治理注册表"""
    start_time = time.perf_counter()
    state = _get_a2a_state(request)
    registry = _get_registry(state)
    audit = _get_audit(state)

    agent_id = body.agent_id or body.did
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id 或 did 必填")

    info = A2AAgentInfo(
        did=agent_id,
        agent_id=agent_id,
        endpoint=body.endpoint,
        public_key_hex=body.public_key_hex,
        skills=body.skill_list,
        capability_card={
            "permission_scope": body.permission_scope,
            "call_constraint": body.call_constraint,
            "memory_policy": body.memory_policy,
        },
    )
    registry.register_agent(info)
    audit.record(event="register", agent_id=agent_id)

    duration = time.perf_counter() - start_time
    record_http_request(
        method=request.method,
        endpoint="a2a/register",
        status=200,
        duration=duration,
    )

    return A2ARegisterResponse(
        success=True,
        agent_id=agent_id,
        message="registered",
    ).to_dict()


@router.get("/discover")
async def a2a_discover(request: Request):
    """Agent 发现 — 返回当前 Agent 的身份和能力"""
    state = _get_a2a_state(request)
    registry = _get_registry(state)
    skills = _get_skills(state)
    did = state.get("did", "")
    alpha_id = state.get("alpha_id", "")

    agents = registry.list_agents()
    if agents:
        return A2ADiscoverResponse(success=True, agent=agents[0]).to_dict()

    return A2ADiscoverResponse(
        success=True,
        agent=A2AAgentInfo(
            did=did,
            endpoint=f"http://localhost:8000",
            skills=[s["name"] for s in skills.list_skills()],
            status="online",
            last_seen=time.time(),
        ).to_dict(),
    ).to_dict()


@router.get("/agents")
async def a2a_list_agents(request: Request):
    """列出所有已注册 Agent"""
    state = _get_a2a_state(request)
    registry = _get_registry(state)
    return registry.to_payload()


@router.get("/skills")
async def a2a_list_skills(request: Request):
    """列出所有可用技能"""
    state = _get_a2a_state(request)
    skills = _get_skills(state)
    return skills.list_skills()


@router.get("/audit")
async def a2a_list_audit(request: Request, query: A2AAuditQuery = ...):
    """查询 A2A 审计日志（支持持久化存储筛选 + 分页）"""
    state = _get_a2a_state(request)
    audit = _get_audit(state)

    # 优先使用持久化存储的分页查询（支持时间范围筛选）
    if hasattr(audit, "list_records") and "start_time" in str(audit.list_records.__code__.co_varnames):
        records = audit.list_records(
            caller_agent_id=query.caller_agent_id,
            start_time=query.start_time or None,
            end_time=query.end_time or None,
            limit=query.limit,
            offset=query.offset,
        )
        total = audit.count(
            caller_agent_id=query.caller_agent_id,
            start_time=query.start_time or None,
            end_time=query.end_time or None,
        )
    else:
        # 降级：内存查询（仅支持 caller_agent_id 过滤）
        records = audit.list_records(caller_agent_id=query.caller_agent_id)
        total = len(records)

    # 客户端侧过滤（target_agent_id, skill）
    if query.target_agent_id:
        records = [r for r in records if r.get("target_agent_id") == query.target_agent_id]
    if query.skill:
        records = [r for r in records if r.get("skill") == query.skill]

    return {"records": records, "total": total}


@router.get("/.well-known/agent.json", response_class=JSONResponse)
async def a2a_agent_card(request: Request):
    """A2A Agent Card（Google A2A 规范：/.well-known/agent.json）

    返回当前 Agent 的能力声明，供其他 Agent 发现和调用。
    参考: https://a2a-protocol.org/specification/
    """
    state = _get_a2a_state(request)
    skills = _get_skills(state)
    registry = _get_registry(state)

    # 构建技能列表（与 Google A2A Agent Card 格式对齐）
    skill_cards = []
    for skill_info in skills.list_skills():
        skill_cards.append({
            "id": skill_info["name"],
            "name": skill_info["name"],
            "description": skill_info.get("description", ""),
            "tags": [],
        })

    # 构建 Agent Card
    card = A2AAgentCard(
        name=state.get("alpha_id", "Alpha-ID Agent"),
        description="Alpha-ID A2A Agent — 身份治理 + 双链记忆 + 可验证执行",
        url=str(request.base_url).rstrip("/"),
        version="0.3.0",
        capabilities=A2ACapability(
            streaming=False,  # Phase 2 将支持 SSE streaming
            push_notifications=False,
            state_transition_history=True,  # PoE 提供执行历史
        ),
        authentication=A2AAuthentication(
            schemes=["bearer", "ed25519"],
        ),
        skills=skill_cards,
        default_input_modes=["text", "application/json"],
        default_output_modes=["text", "application/json"],
    )

    return JSONResponse(content=card.model_dump(mode="json"))


@router.get("/health")
async def a2a_health(request: Request):
    """A2A 健康检查"""
    state = _get_a2a_state(request)
    return {
        "status": "ok",
        "did": state.get("did", ""),
        "alpha_id": state.get("alpha_id", ""),
        "skills_count": len(_get_skills(state).list_skills()),
        "agents_count": len(_get_registry(state).list_agents()),
    }


# ── 内部辅助函数 ──


def _write_a2a_memory(
    container: Container,
    alpha_id: str,
    call_req: A2ACallRequest,
    result: Any,
    success: bool,
    elapsed_ms: float,
    error: str = "",
    dual_chain_cache: Dict[str, Any] = None,
) -> None:
    """A2A 调用结果回写双链记忆（best-effort，不阻塞主流程）

    Args:
        dual_chain_cache: 预创建的 DualChainManager 缓存（避免每次调用都 PBKDF2）
    """
    try:
        from core.dual_chain import DualChainManager

        # 缓存 DualChainManager：避免每次调用都做 PBKDF2 (100k iterations)
        if dual_chain_cache is None:
            dual_chain_cache = {}
        if alpha_id not in dual_chain_cache:
            dual_chain_cache[alpha_id] = DualChainManager(alpha_id=alpha_id, storage=container.storage)
        mgr = dual_chain_cache[alpha_id]

        status = "success" if success else f"error: {error}"
        content = (
            f"[A2A] {call_req.caller} → {call_req.target}.{call_req.skill} "
            f"| {status} | {elapsed_ms:.1f}ms"
        )
        if result is not None and success:
            content += f" | result: {str(result)[:200]}"

        mgr.save(
            content=content,
            category="a2a_call",
            sensitivity="knowledge",
            source=f"a2a:{call_req.request_id}",
            tags=["a2a", call_req.skill, "success" if success else "failed"],
        )
    except Exception as exc:
        logger.debug("A2A 双链回写失败（非阻塞）: %s", exc)


def _record_a2a_call(
    caller: str,
    target: str,
    skill: str,
    success: bool,
    duration: float,
) -> None:
    """记录 A2A 调用指标到 observability"""
    try:
        record_http_request(
            method="A2A",
            endpoint=f"{target}.{skill}",
            status=200 if success else 500,
            duration=duration,
        )
    except Exception:
        pass
