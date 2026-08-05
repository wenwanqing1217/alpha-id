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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    # ── 用户 a-to-a 字段 ──
    caller_alpha_id: str = Field("", description="调用方用户 alpha_id（用于计费 + 社交授权）")
    api_key: str = Field("", description="调用方 API Key（简化模式代替 proof）")


class A2ARegisterBody(BaseModel):
    """Agent 注册请求体

    支持两种接入模式：
      1. Ed25519 签名模式（高安全）：填 public_key_hex
      2. API Key 简化模式（用户友好）：填 api_key，可不填 public_key_hex
    """
    agent_id: str = Field("", description="Agent ID")
    name: str = Field("", description="Agent 显示名（市场展示用）")
    did: str = Field("", description="DID")
    endpoint: str = Field("", description="Agent 端点地址")
    public_key_hex: str = Field("", description="公钥 hex（Ed25519 模式）")
    api_key: str = Field("", description="API Key（简化接入模式，替代 Ed25519）")
    skill_list: List[str] = Field(default_factory=list, description="技能列表")
    permission_scope: List[str] = Field(default_factory=list)
    call_constraint: Dict[str, Any] = Field(default_factory=dict)
    memory_policy: str = Field("write_summary")
    # ── 用户 a-to-a 字段 ──
    owner_alpha_id: str = Field("", description="归属用户 alpha_id（空=平台基建）")
    category: str = Field("", description="市场分类（视频/文案/资讯/翻译...）")
    price_credits: int = Field(0, ge=0, description="调用一次的积分价格（0=免费）")
    description: str = Field("", description="Agent 描述（市场展示）")
    auto_submit: bool = Field(True, description="是否自动提交审核（默认 True）")


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

    # ── 用户 a-to-a 社交授权 + 预算检查 ──
    # 仅当调用方提供了 caller_alpha_id 时启用计费链路（机器调用走传统路径）
    billing_info: Dict[str, Any] = {"charged": False, "price": 0, "reason": "no_billing"}
    target_node = None
    if body.caller_alpha_id:
        try:
            from core.agent_graph import get_agent_graph
            graph = get_agent_graph()
            target_node = graph.get_agent(call_req.target)
        except Exception as e:
            logger.warning("AgentGraph 查询失败: %s", e)

        if target_node:
            # 状态可见性检查：非 approved 状态的 agent 只允许 owner 自己调用
            if target_node.status != "approved":
                if target_node.owner_alpha_id != body.caller_alpha_id:
                    audit.record(
                        event="social_denied",
                        caller_agent_id=call_req.caller,
                        target_agent_id=call_req.target,
                        skill=call_req.skill,
                        request_id=call_req.request_id,
                        error=f"target status={target_node.status} 非 owner 不可调用",
                    )
                    return JSONResponse(
                        A2ACallResponse(
                            success=False,
                            error=f"Agent {call_req.target} 当前状态 {target_node.status}，不可调用",
                            request_id=call_req.request_id,
                        ).to_dict(),
                        status_code=403,
                    )

            # 判断社交关系 + 预算
            owner_alpha_id = target_node.owner_alpha_id
            price = target_node.price_credits

            # 决定是否需要付费
            is_friend = False
            if owner_alpha_id and owner_alpha_id != body.caller_alpha_id and price > 0:
                # 陌生人调用，需要付费 → 检查余额
                try:
                    social_mgr = container.social
                    is_friend = owner_alpha_id in social_mgr.get_friends(body.caller_alpha_id)
                except Exception as e:
                    logger.warning("好友关系查询失败: %s", e)
                    is_friend = False

                if not is_friend:
                    # 陌生人付费 → 余额预检
                    try:
                        credits_mgr = container.credits
                        balance = credits_mgr.balance(body.caller_alpha_id)
                        if balance < price:
                            audit.record(
                                event="insufficient_balance",
                                caller_agent_id=call_req.caller,
                                target_agent_id=call_req.target,
                                skill=call_req.skill,
                                request_id=call_req.request_id,
                                error=f"balance={balance} < price={price}",
                            )
                            return JSONResponse(
                                A2ACallResponse(
                                    success=False,
                                    error=f"积分不足：需要 {price}，当前余额 {balance}",
                                    request_id=call_req.request_id,
                                ).to_dict(),
                                status_code=402,  # Payment Required
                            )
                    except Exception as e:
                        logger.warning("余额检查失败: %s", e)

            billing_info = {
                "charged": False,  # 执行成功后才扣，先标记
                "price": price,
                "reason": "pending",
                "owner_alpha_id": owner_alpha_id,
                "is_friend": is_friend,
                "caller_alpha_id": body.caller_alpha_id,
            }

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

        # 记录 AgentGraph 调用边 + 统计
        if target_node is not None:
            try:
                from core.agent_graph import get_agent_graph
                get_agent_graph().record_call(
                    caller=call_req.caller,
                    target=call_req.target,
                    skill=call_req.skill,
                    success=True,
                    latency_ms=elapsed,
                )
                target_node.total_calls += 1
            except Exception as e:
                logger.warning("AgentGraph 记录调用失败: %s", e)

        # ── 用户 a-to-a 计费结算（执行成功才扣分） ──
        if body.caller_alpha_id and target_node is not None:
            try:
                credits_mgr = container.credits
                settlement = credits_mgr.settle_call(
                    caller_alpha_id=body.caller_alpha_id,
                    owner_alpha_id=target_node.owner_alpha_id,
                    price_credits=target_node.price_credits,
                    agent_id=call_req.target,
                    skill=call_req.skill,
                    request_id=call_req.request_id,
                    is_friend=billing_info.get("is_friend"),
                )
                billing_info = settlement
                audit.record(
                    event="billing_settled",
                    caller_agent_id=call_req.caller,
                    target_agent_id=call_req.target,
                    skill=call_req.skill,
                    request_id=call_req.request_id,
                    success=True,
                    error=str(settlement),
                )
            except Exception as e:
                # 计费失败不应回滚已成功的调用，但需审计记录
                logger.error("计费结算失败: %s", e, exc_info=True)
                audit.record(
                    event="billing_failed",
                    caller_agent_id=call_req.caller,
                    target_agent_id=call_req.target,
                    skill=call_req.skill,
                    request_id=call_req.request_id,
                    success=False,
                    error=str(e),
                )
                billing_info = {"charged": False, "price": 0, "reason": f"billing_error: {e}"}

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

        response = A2ACallResponse(
            success=True,
            result=result,
            request_id=call_req.request_id,
            executor=did,
            proof=proof,
            execution_time_ms=elapsed,
        ).to_dict()
        # 附带计费信息给调用方
        response["billing"] = billing_info
        return response

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

        # 失败也记录调用边（不计费）
        if target_node is not None:
            try:
                from core.agent_graph import get_agent_graph
                get_agent_graph().record_call(
                    caller=call_req.caller,
                    target=call_req.target,
                    skill=call_req.skill,
                    success=False,
                    latency_ms=elapsed,
                )
            except Exception:
                pass

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
    """Agent 注册 — 将 Agent 加入治理注册表 + AgentGraph

    支持两种接入模式：
      1. Ed25519 模式：填 public_key_hex（高安全，机器对机器）
      2. API Key 模式：填 api_key（简化，用户 DIY 接入）

    状态机：
      - 平台基建 agent（owner_alpha_id 空）→ approved（直接上架）
      - 用户 agent（owner_alpha_id 非空）+ auto_submit=True → submitted（待审核）
      - 用户 agent + auto_submit=False → pending（草稿）
    """
    start_time = time.perf_counter()
    state = _get_a2a_state(request)
    registry = _get_registry(state)
    audit = _get_audit(state)

    agent_id = body.agent_id or body.did
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id 或 did 必填")

    # 至少要有一种认证方式
    if not body.public_key_hex and not body.api_key:
        raise HTTPException(
            status_code=400,
            detail="必须提供 public_key_hex 或 api_key 之一",
        )

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
            # 用户 a-to-a 扩展字段
            "owner_alpha_id": body.owner_alpha_id,
            "category": body.category,
            "price_credits": body.price_credits,
            "api_key": body.api_key,  # 简化接入模式
            "auth_mode": "api_key" if body.api_key and not body.public_key_hex else "ed25519",
        },
    )
    registry.register_agent(info)
    audit.record(event="register", agent_id=agent_id)

    # 同步注册到 AgentGraph（让总助能发现并调用）
    # 状态机决策：
    #   - 平台基建（owner 空）→ approved
    #   - 用户 agent + auto_submit → submitted（等审核）
    #   - 用户 agent + 不 auto_submit → pending（草稿，仅自己可见）
    if not body.owner_alpha_id:
        initial_status = "approved"
    elif body.auto_submit:
        initial_status = "submitted"
    else:
        initial_status = "pending"

    try:
        from core.agent_graph import get_agent_graph, AgentNode
        graph = get_agent_graph()
        graph.register_agent(AgentNode(
            agent_id=agent_id,
            name=body.name or body.agent_id or agent_id,
            agent_type="external",  # 用户 DIY 接入标记为 external
            endpoint=body.endpoint,
            skills=body.skill_list or [],
            is_free=(body.price_credits == 0),
            description=body.description or f"DIY agent by {body.owner_alpha_id or agent_id}",
            owner_alpha_id=body.owner_alpha_id,
            status=initial_status,
            price_credits=body.price_credits,
            api_key=body.api_key,
            category=body.category,
            metadata={
                "public_key": body.public_key_hex,
                "permission_scope": body.permission_scope,
                "auth_mode": "api_key" if body.api_key and not body.public_key_hex else "ed25519",
            },
        ))
        audit.record(
            event="agent_graph_register",
            agent_id=agent_id,
            success=True,
            error=str({"status": initial_status, "owner": body.owner_alpha_id}),
        )
    except Exception as e:
        logger.warning("AgentGraph 注册失败: %s", e)
        audit.record(
            event="agent_graph_register",
            agent_id=agent_id,
            success=False,
            error=str(e),
        )

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
        message=f"registered (status={initial_status})",
    ).to_dict()


# ── 上架审核状态机 ──────────────────────────────────────────────
# pending（草稿）→ submitted（待审核）→ approved（已上架）
#                                          ↓
#                                       delisted（已下架）
#                                          ↓
#                                       approved（重新上架）


def _check_admin(authorization: Optional[str]) -> bool:
    """简易管理员校验（实际项目可对接 JWT role）

    通过环境变量 ADMIN_ALPHA_IDS（逗号分隔）配置管理员列表。
    """
    import os
    admin_ids = {x.strip() for x in os.getenv("ADMIN_ALPHA_IDS", "").split(",") if x.strip()}
    if not admin_ids:
        return True  # 未配置管理员时允许（开发模式），生产应配置
    try:
        from auth.jwt import get_current_alpha_id
        alpha_id = get_current_alpha_id(authorization)
        return alpha_id in admin_ids
    except Exception:
        return False


@router.post("/agents/{agent_id}/submit")
async def a2a_submit_for_review(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = None,
):
    """提交审核：pending → submitted（用户提交自己的 agent 进入审核）"""
    from core.agent_graph import get_agent_graph
    graph = get_agent_graph()
    node = graph.get_agent(agent_id)
    if not node:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    if node.status not in ("pending", "delisted", "submitted"):
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {node.status} 不允许提交审核",
        )

    node.status = "submitted"
    audit = _get_audit(_get_a2a_state(request))
    audit.record(event="agent_submit", agent_id=agent_id, success=True)
    return {"success": True, "agent_id": agent_id, "status": "submitted"}


@router.post("/agents/{agent_id}/approve")
async def a2a_approve_agent(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = None,
):
    """管理员通过审核：submitted → approved（agent 上架到市场）"""
    if not _check_admin(authorization):
        raise HTTPException(status_code=403, detail="需要管理员权限")

    from core.agent_graph import get_agent_graph
    graph = get_agent_graph()
    node = graph.get_agent(agent_id)
    if not node:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    if node.status != "submitted":
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {node.status} 不允许通过审核（需先 submit）",
        )

    node.status = "approved"
    audit = _get_audit(_get_a2a_state(request))
    audit.record(event="agent_approve", agent_id=agent_id, success=True)
    return {"success": True, "agent_id": agent_id, "status": "approved"}


@router.post("/agents/{agent_id}/delist")
async def a2a_delist_agent(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = None,
):
    """下架：approved → delisted（owner 自愿下架 / 管理员强制下架）"""
    from core.agent_graph import get_agent_graph
    graph = get_agent_graph()
    node = graph.get_agent(agent_id)
    if not node:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    if node.status != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {node.status} 不允许下架（必须为 approved）",
        )

    node.status = "delisted"
    audit = _get_audit(_get_a2a_state(request))
    audit.record(event="agent_delist", agent_id=agent_id, success=True)
    return {"success": True, "agent_id": agent_id, "status": "delisted"}


@router.post("/agents/{agent_id}/relist")
async def a2a_relist_agent(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = None,
):
    """重新上架：delisted → approved（owner 重新上架已下架的 agent）"""
    from core.agent_graph import get_agent_graph
    graph = get_agent_graph()
    node = graph.get_agent(agent_id)
    if not node:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    if node.status != "delisted":
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {node.status} 不允许重新上架（必须为 delisted）",
        )

    node.status = "approved"
    audit = _get_audit(_get_a2a_state(request))
    audit.record(event="agent_relist", agent_id=agent_id, success=True)
    return {"success": True, "agent_id": agent_id, "status": "approved"}


@router.get("/agents/{agent_id}")
async def a2a_get_agent_detail(
    agent_id: str,
    request: Request,
):
    """获取单个 agent 详情（含状态、价格、统计）"""
    from core.agent_graph import get_agent_graph
    graph = get_agent_graph()
    node = graph.get_agent(agent_id)
    if not node:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    # 脱敏：不返回 api_key 和 public_key
    safe = {
        "agent_id": node.agent_id,
        "name": node.name,
        "type": node.agent_type,
        "endpoint": node.endpoint,
        "skills": node.skills,
        "is_free": node.is_free,
        "is_online": node.is_online,
        "description": node.description,
        "owner_alpha_id": node.owner_alpha_id,
        "status": node.status,
        "price_credits": node.price_credits,
        "category": node.category,
        "rating": node.rating,
        "total_calls": node.total_calls,
        "registered_at": node.registered_at,
        "last_heartbeat": node.last_heartbeat,
        "stats": graph.get_agent_stats(node.agent_id),
    }
    return safe


def _node_to_safe_dict(node, stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """脱敏 agent 节点 → dict（市场列表用）"""
    return {
        "agent_id": node.agent_id,
        "name": node.name,
        "type": node.agent_type,
        "endpoint": node.endpoint,
        "skills": node.skills,
        "is_free": node.is_free,
        "is_online": node.is_online,
        "description": node.description,
        "owner_alpha_id": node.owner_alpha_id,
        "status": node.status,
        "price_credits": node.price_credits,
        "category": node.category,
        "rating": node.rating,
        "total_calls": node.total_calls,
        "registered_at": node.registered_at,
        "last_heartbeat": node.last_heartbeat,
        "stats": stats or {},
    }


@router.get("/market")
async def a2a_agent_market(
    request: Request,
    q: str = Query("", description="搜索关键词"),
    category: str = Query("", description="分类过滤"),
    owner: str = Query("", description="仅看某 owner 的 agent"),
    status: str = Query("", description="状态过滤（默认只看 approved）"),
    limit: int = Query(50, ge=1, le=200),
):
    """Agent 市场 — 列出/搜索已上架的 agent

    默认只返回 approved 状态（已审核通过）。
    通过 owner 参数可查看自己的 agent（含未上架的）。
    """
    from core.agent_graph import get_agent_graph
    graph = get_agent_graph()

    # 如果指定 owner，使用 list_agents（含未上架）
    if owner:
        nodes = graph.list_agents(
            owner_alpha_id=owner,
            category=category or None,
            include_unlisted=True,  # owner 看自己的全部
            viewer_alpha_id=owner,
        )
    else:
        # 公共市场：只看 approved
        nodes = graph.search_agents(
            query=q,
            category=category or None,
            viewer_alpha_id="",
            include_unlisted=False,
            limit=limit,
        )

    items = [_node_to_safe_dict(n, graph.get_agent_stats(n.agent_id)) for n in nodes]
    return {
        "items": items,
        "count": len(items),
        "filters": {"q": q, "category": category, "owner": owner, "status": status},
    }


@router.get("/categories")
async def a2a_list_categories(request: Request):
    """列出所有 agent 分类（市场筛选用）"""
    from core.agent_graph import get_agent_graph
    graph = get_agent_graph()
    categories: Dict[str, int] = {}
    for node in graph.list_agents():
        if node.status != "approved":
            continue
        cat = node.category or "未分类"
        categories[cat] = categories.get(cat, 0) + 1
    return {"categories": categories}


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


@router.get("/graph")
async def a2a_agent_graph(request: Request):
    """A2A Agent 网络拓扑图（nodes + edges）

    优先使用 AgentGraph（含内部 agent + 统计 + findskill），
    回退到旧逻辑（registry + audit log 现算）。
    """
    try:
        from core.agent_graph import get_agent_graph
        graph = get_agent_graph()
        topology = graph.get_topology()
        # 兼容旧格式（from/to 字段名）
        for edge in topology["edges"]:
            edge["from"] = edge.get("source", "")
            edge["to"] = edge.get("target", "")
        return topology
    except Exception:
        pass

    # 回退：旧逻辑
    state = _get_a2a_state(request)
    registry = _get_registry(state)
    audit = _get_audit(state)

    agents_payload = registry.to_payload()
    nodes = []
    for info in agents_payload.get("agents", []):
        did = info.get("did", "")
        nodes.append({
            "id": did,
            "label": info.get("alpha_id", did),
            "endpoint": info.get("endpoint", ""),
            "skills": info.get("skill_list", []),
            "group": "agent",
        })

    edges = []
    seen = set()
    try:
        records = audit.list_records()
        for rec in records:
            caller = rec.get("caller_agent_id", "")
            target = rec.get("target_agent_id", "")
            skill = rec.get("skill", "")
            if not caller or not target:
                continue
            key = (caller, target, skill)
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "from": caller,
                "to": target,
                "skill": skill,
                "timestamp": rec.get("timestamp", ""),
            })
    except Exception:
        pass

    return {"nodes": nodes, "edges": edges}


@router.get("/findskill")
async def a2a_find_skill(
    request: Request,
    skill: str,
    prefer: str = "free",
):
    """findskill — 查找提供指定 skill 的最优 agent

    这是 AgentGraph 的核心能力：总助通过这个端点找到该调用哪个 agent。

    Query params:
        skill:  skill 名称（如 video_generate / channel_copy / feed_github）
        prefer: 选路策略 free / fast / reliable / any
    """
    try:
        from core.agent_graph import get_agent_graph
        graph = get_agent_graph()

        candidates = graph.find_skill(skill)
        best = graph.find_best_agent(skill, prefer=prefer)

        return {
            "success": True,
            "skill": skill,
            "prefer": prefer,
            "best_agent": {
                "agent_id": best.agent_id,
                "name": best.name,
                "type": best.agent_type,
                "endpoint": best.endpoint,
                "is_free": best.is_free,
                "description": best.description,
            } if best else None,
            "candidates": [
                {
                    "agent_id": c.agent_id,
                    "name": c.name,
                    "type": c.agent_type,
                    "is_free": c.is_free,
                    "is_online": c.is_online,
                    "stats": graph.get_agent_stats(c.agent_id),
                }
                for c in candidates
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/skills")
async def a2a_list_skills(request: Request):
    """列出所有可用技能"""
    state = _get_a2a_state(request)
    skills = _get_skills(state)
    return skills.list_skills()


@router.get("/audit")
async def a2a_list_audit(
    request: Request,
    caller_agent_id: str = Query("", description="按调用方过滤"),
    target_agent_id: str = Query("", description="按目标过滤"),
    skill: str = Query("", description="按技能名过滤"),
    start_time: str = Query("", description="起始时间 (ISO 格式)"),
    end_time: str = Query("", description="结束时间 (ISO 格式)"),
    limit: int = Query(100, ge=1, le=1000, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """查询 A2A 审计日志（支持持久化存储筛选 + 分页）"""
    state = _get_a2a_state(request)
    audit = _get_audit(state)

    # 优先使用持久化存储的分页查询（支持时间范围筛选）
    if hasattr(audit, "list_records") and "start_time" in str(audit.list_records.__code__.co_varnames):
        records = audit.list_records(
            caller_agent_id=caller_agent_id,
            start_time=start_time or None,
            end_time=end_time or None,
            limit=limit,
            offset=offset,
        )
        total = audit.count(
            caller_agent_id=caller_agent_id,
            start_time=start_time or None,
            end_time=end_time or None,
        )
    else:
        # 降级：内存查询（仅支持 caller_agent_id 过滤）
        records = audit.list_records(caller_agent_id=caller_agent_id)
        total = len(records)

    # 客户端侧过滤（target_agent_id, skill）
    if target_agent_id:
        records = [r for r in records if r.get("target_agent_id") == target_agent_id]
    if skill:
        records = [r for r in records if r.get("skill") == skill]

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
