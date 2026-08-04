# TERM: AlphaSocialManager — 社交管理器（好友请求 + 消息 + EventBus 发布）
"""社交网络 API 路由"""

from fastapi import APIRouter, Depends, HTTPException, Query

from alpha_id.container import Container, get_container
from auth.middleware import require_user
from core.alpha_social import AlphaSocialManager

from .models import FriendRequestRespond, FriendRequestSend, MessageSend

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
