# TERM: AlphaSocialManager — 社交管理器（好友请求 + 消息 + EventBus 发布 + 飞书通讯录同步）
"""社交网络 API 路由"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from alpha_id.container import Container, get_container
from auth.middleware import require_user
from core.alpha_social import AlphaSocialManager, UserBinding

from .models import FriendRequestRespond, FriendRequestSend, MessageSend


class FeishuBinding(BaseModel):
    """飞书账号绑定体（DS「绑定飞书」按钮调用）"""
    alpha_id: str = Field(..., description="平台 Alpha-ID")
    feishu_open_id: str = Field("", description="飞书 open_id（最推荐）")
    feishu_user_id: str = Field("", description="飞书 user_id/employee_id")
    feishu_union_id: str = Field("", description="飞书 union_id（跨应用唯一）")
    phone: str = Field("", description="手机号（可选）")
    email: str = Field("", description="邮箱（可选）")
    metadata: Dict[str, Any] = Field(default_factory=dict)

router = APIRouter(prefix="/api/v1/social", tags=["社交"])


def get_manager(container: Container = Depends(get_container)) -> AlphaSocialManager:
    """依赖注入：从 Container 获取 AlphaSocialManager"""
    return container.social


@router.post("/friend-request")
def send_friend_request(body: FriendRequestSend,
                        _: str = Depends(require_user),
                        manager: AlphaSocialManager = Depends(get_manager)):
    """发送好友请求"""
    result = manager.send_friend_request(
        from_alpha_id=body.from_alpha_id,
        to_alpha_id=body.to_alpha_id,
        message=body.message,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.put("/friend-request/{request_id}")
def respond_friend_request(request_id: str,
                           body: FriendRequestRespond,
                           _: str = Depends(require_user),
                           manager: AlphaSocialManager = Depends(get_manager)):
    """响应好友请求"""
    result = manager.respond_friend_request(request_id=request_id, response=body.response)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/{alpha_id}/friends")
def get_friends(alpha_id: str,
                _: str = Depends(require_user),
                manager: AlphaSocialManager = Depends(get_manager)):
    """获取好友列表"""
    friends = manager.get_friends(alpha_id)
    return {"alpha_id": alpha_id, "friends": friends, "count": len(friends)}


@router.get("/{alpha_id}/requests")
def get_pending_requests(alpha_id: str,
                         _: str = Depends(require_user),
                         manager: AlphaSocialManager = Depends(get_manager)):
    """获取待处理的好友请求"""
    requests = manager.get_pending_friend_requests(alpha_id)
    return {"alpha_id": alpha_id, "requests": requests, "count": len(requests)}


@router.post("/message")
def send_message(body: MessageSend,
                 _: str = Depends(require_user),
                 manager: AlphaSocialManager = Depends(get_manager)):
    """发送消息给好友"""
    result = manager.send_message(
        from_alpha_id=body.from_alpha_id,
        to_alpha_id=body.to_alpha_id,
        content=body.content,
        message_type=body.message_type,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/{alpha_id}/messages")
def get_messages(alpha_id: str,
                 unread_only: bool = Query(False),
                 _: str = Depends(require_user),
                 manager: AlphaSocialManager = Depends(get_manager)):
    """获取消息列表"""
    messages = manager.get_messages(alpha_id, unread_only=unread_only)
    return {"alpha_id": alpha_id, "messages": messages, "count": len(messages)}


# ── 飞书绑定 & 通讯录同步 ──

@router.post("/{alpha_id}/bind/feishu")
def bind_feishu(
    alpha_id: str,
    body: FeishuBinding,
    _: str = Depends(require_user),
    manager: AlphaSocialManager = Depends(get_manager),
):
    """绑定飞书账号到指定 Alpha-ID

    DS 侧先通过飞书 OAuth 拿到 open_id 等，再 POST 到这里，
    之后 sync_contacts 调用就会自动把飞书同事互认为平台好友。
    """
    if body.alpha_id and body.alpha_id != alpha_id:
        raise HTTPException(status_code=400, detail="路径 alpha_id 与 body.alpha_id 不一致")
    b = UserBinding(
        alpha_id=alpha_id,
        feishu_open_id=body.feishu_open_id,
        feishu_user_id=body.feishu_user_id,
        feishu_union_id=body.feishu_union_id,
        phone=body.phone,
        email=body.email,
        metadata=body.metadata,
    )
    manager.set_user_binding(b)
    return {"success": True, "alpha_id": alpha_id, "message": "飞书绑定成功"}


@router.get("/{alpha_id}/bind")
def get_binding(
    alpha_id: str,
    _: str = Depends(require_user),
    manager: AlphaSocialManager = Depends(get_manager),
):
    """查询当前绑定信息（脱敏：不返回原 ID，只返回是否已绑）"""
    b = manager.get_user_binding(alpha_id)
    if b is None:
        return {
            "alpha_id": alpha_id,
            "bound": False,
            "feishu": False,
            "wechat": False,
            "telegram": False,
        }
    return {
        "alpha_id": alpha_id,
        "bound": True,
        "feishu": bool(b.feishu_open_id or b.feishu_user_id or b.feishu_union_id),
        "wechat": bool(b.wechat_open_id),
        "telegram": bool(b.tg_user_id),
        "phone": bool(b.phone),
        "email": bool(b.email),
        "updated_at": b.updated_at,
    }


@router.post("/{alpha_id}/sync-feishu-contacts")
def sync_feishu_contacts(
    alpha_id: str,
    _: str = Depends(require_user),
    manager: AlphaSocialManager = Depends(get_manager),
):
    """主动同步飞书通讯录，自动把飞书同事 + 已绑定平台用户互认为好友

    返回 {fetched_contacts, matched_platform_users, auto_friends_added}
    """
    result = manager.sync_feishu_contacts(actor_alpha_id=alpha_id)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "同步失败"))
    return result
