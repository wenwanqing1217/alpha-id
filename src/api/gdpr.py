"""GDPR / 个保法合规 API — 数据导出与删除

提供用户数据主权功能：
  - GET  /api/v1/gdpr/export  — 导出全部个人数据（JSON）
  - DELETE /api/v1/gdpr/delete — 删除全部个人数据（被遗忘权）
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from alpha_id.container import Container
from auth.middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gdpr", tags=["GDPR / 数据主权"])


class DeleteRequest(BaseModel):
    """数据删除请求 — 需要确认码防止误操作"""

    confirmation: str = Field(
        ...,
        description="确认码，必须等于 alpha_id 以确认删除",
    )


class ExportResponse(BaseModel):
    """数据导出响应元数据"""

    alpha_id: str
    exported_at: str
    data: Dict[str, Any]


# ── 辅助函数 ──


def _collect_user_data(alpha_id: str) -> Dict[str, Any]:
    """收集用户全部个人数据"""
    container = Container.instance()
    storage = container.storage

    # 基础档案
    profile = container.identity.get_user_profile(alpha_id) or {}

    # 双链记忆
    memories: Dict[str, list] = {"private": [], "knowledge": []}
    try:
        if hasattr(container, "dual_chain") and container.dual_chain:
            dual = container.dual_chain
            memories["private"] = dual.query(chain="private", limit=1000) or []
            memories["knowledge"] = dual.query(chain="knowledge", limit=1000) or []
    except Exception as exc:
        logger.warning("Failed to export memories for %s: %s", alpha_id, exc)

    # 社交数据
    social: Dict[str, Any] = {}
    try:
        if hasattr(container, "social") and container.social:
            social_mgr = container.social
            social["friends"] = social_mgr.get_friends(alpha_id) or []
            social["requests"] = social_mgr.get_pending_requests(alpha_id) or []
    except Exception as exc:
        logger.warning("Failed to export social data for %s: %s", alpha_id, exc)

    return {
        "profile": profile,
        "memories": memories,
        "social": social,
    }


def _delete_user_data(alpha_id: str) -> Dict[str, int]:
    """删除用户全部个人数据，返回删除统计"""
    container = Container.instance()
    stats: Dict[str, int] = {"memories": 0, "social": 0, "profile": 0}

    # 删除双链记忆
    try:
        if hasattr(container, "dual_chain") and container.dual_chain:
            dual = container.dual_chain
            private_mem = dual.query(chain="private", limit=10000) or []
            knowledge_mem = dual.query(chain="knowledge", limit=10000) or []
            for mem in private_mem + knowledge_mem:
                mem_id = mem.get("id", "")
                if mem_id:
                    dual.delete(mem_id)
                    stats["memories"] += 1
    except Exception as exc:
        logger.error("Failed to delete memories for %s: %s", alpha_id, exc)

    # 删除社交数据
    try:
        if hasattr(container, "social") and container.social:
            social_mgr = container.social
            friends = social_mgr.get_friends(alpha_id) or []
            for friend_id in friends:
                social_mgr.remove_friend(alpha_id, friend_id)
                stats["social"] += 1
    except Exception as exc:
        logger.error("Failed to delete social data for %s: %s", alpha_id, exc)

    # 删除用户档案
    try:
        container.identity.delete_user(alpha_id)
        stats["profile"] = 1
    except Exception as exc:
        logger.error("Failed to delete profile for %s: %s", alpha_id, exc)

    return stats


# ── 端点 ──


@router.get("/export", response_model=ExportResponse)
def export_data(alpha_id: str = Depends(require_user)):
    """导出全部个人数据（JSON 格式）"""
    data = _collect_user_data(alpha_id)
    return ExportResponse(
        alpha_id=alpha_id,
        exported_at=datetime.utcnow().isoformat() + "Z",
        data=data,
    )


@router.delete("/delete")
def delete_data(body: DeleteRequest, alpha_id: str = Depends(require_user)):
    """删除全部个人数据（被遗忘权）— 需要确认码"""
    # 安全校验：确认码必须等于 alpha_id
    if body.confirmation != alpha_id:
        raise HTTPException(
            status_code=400,
            detail="确认码错误：请传入您的 alpha_id 以确认删除",
        )

    stats = _delete_user_data(alpha_id)
    logger.info("User %s deleted all data: %s", alpha_id, stats)

    return {
        "success": True,
        "message": "您的全部个人数据已被删除",
        "stats": stats,
        "deleted_at": datetime.utcnow().isoformat() + "Z",
    }
