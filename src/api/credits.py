# TERM: Credits — 积分系统（社交免费 + 陌生人付费）
"""Credits Wallet API 路由

提供：
  GET  /api/v1/credits/wallet              查询钱包摘要
  GET  /api/v1/credits/balance             查询余额（轻量）
  GET  /api/v1/credits/transactions        交易流水
  POST /api/v1/credits/reward              得分（管理员/系统调用）
  POST /api/v1/credits/refund/{tx_id}      退款
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from alpha_id.container import Container, get_container
from auth.middleware import require_user
from core.credits import CreditsManager, InsufficientBalanceError

logger = logging.getLogger(__name__)


def _tx_to_dict(tx) -> Dict[str, Any]:
    """将 Transaction dataclass 转 dict（兼容 asdict）"""
    try:
        return asdict(tx)
    except TypeError:
        return dict(tx)

router = APIRouter(prefix="/api/v1/credits", tags=["积分钱包"])


def get_credits(container: Container = Depends(get_container)) -> CreditsManager:
    """依赖注入：从 Container 获取 CreditsManager"""
    return container.credits


class RewardBody(BaseModel):
    """得分请求体（系统/管理员调用）"""
    alpha_id: str = Field(..., description="目标用户")
    amount: int = Field(..., ge=0, description="积分数")
    reason: str = Field("reward", description="原因")
    counterparty: str = Field("", description="对手方")
    agent_id: str = Field("", description="关联 agent")
    skill: str = Field("", description="关联 skill")
    request_id: str = Field("", description="A2A request_id")
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.get("/wallet")
def get_wallet_summary(
    alpha_id: str = Depends(require_user),
    credits: CreditsManager = Depends(get_credits),
):
    """查询当前用户钱包摘要"""
    return credits.get_wallet_summary(alpha_id)


@router.get("/wallet/{alpha_id}")
def get_wallet_by_id(
    alpha_id: str,
    _: str = Depends(require_user),
    credits: CreditsManager = Depends(get_credits),
):
    """查询指定用户钱包（需登录，权限由上层控制）"""
    return credits.get_wallet_summary(alpha_id)


@router.get("/balance")
def get_balance(
    alpha_id: str = Depends(require_user),
    credits: CreditsManager = Depends(get_credits),
):
    """查询余额（轻量接口，前端高频轮询用）"""
    return {"alpha_id": alpha_id, "balance": credits.balance(alpha_id)}


@router.get("/transactions")
def list_transactions(
    alpha_id: str = Depends(require_user),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    direction: Optional[str] = Query(None, description="credit / debit"),
    credits: CreditsManager = Depends(get_credits),
):
    """查询交易流水"""
    items = credits.get_transactions(
        alpha_id=alpha_id,
        limit=limit,
        offset=offset,
        direction=direction,
    )
    return {
        "alpha_id": alpha_id,
        "items": items,
        "count": len(items),
        "limit": limit,
        "offset": offset,
    }


@router.post("/reward")
def reward_user(
    body: RewardBody,
    _: str = Depends(require_user),
    credits: CreditsManager = Depends(get_credits),
):
    """得分（管理员/系统调用，普通用户调用受业务层限制）

    注意：此端点本身不做权限分级，权限由 require_user + 业务规则在调用方控制。
    A2A 调用产生的得分应通过 CreditsManager.settle_call 完成，不走这个端点。
    """
    try:
        tx = credits.reward(
            alpha_id=body.alpha_id,
            amount=body.amount,
            reason=body.reason,
            counterparty=body.counterparty,
            agent_id=body.agent_id,
            skill=body.skill,
            request_id=body.request_id,
            metadata=body.metadata,
        )
        return {"success": True, "tx": _tx_to_dict(tx)}
    except Exception as e:
        logger.exception("reward 失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refund/{tx_id}")
def refund_tx(
    tx_id: str,
    _: str = Depends(require_user),
    credits: CreditsManager = Depends(get_credits),
):
    """退款（按原扣分交易 ID 等额返还）"""
    tx = credits.refund(tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="未找到原扣分交易或不可退款")
    return {"success": True, "tx": _tx_to_dict(tx)}
