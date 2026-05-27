"""
Alpha-ID 社交互动工具（框架胶水层）

仅保留 @tool 装饰的函数，核心逻辑在 core.alpha_social 中。
"""

import json
from langchain.tools import tool, ToolRuntime
from coze_coding_utils.runtime_ctx.context import new_context

from core.alpha_social import AlphaSocialManager


# 全局管理器实例
_social_manager = AlphaSocialManager()


# ================== 工具函数 ==================

@tool
def send_alpha_friend_request(
    target_alpha_id: str,
    message: str,
    runtime: ToolRuntime = None
) -> str:
    """
    发送好友请求到另一个Alpha

    Args:
        target_alpha_id: 目标Alpha-ID（例如：Alpha-001）
        message: 请求消息

    Returns:
        操作结果
    """
    ctx = runtime.context if runtime else new_context(method="send_alpha_friend_request")
    from_alpha_id = "Alpha-1"  # 默认为创始人
    if not from_alpha_id.startswith("Alpha-"):
        from_alpha_id = f"Alpha-{from_alpha_id}"

    result = _social_manager.send_friend_request(
        from_alpha_id=from_alpha_id,
        to_alpha_id=target_alpha_id,
        message=message
    )
    return json.dumps(result, ensure_ascii=False)


@tool
def respond_to_alpha_friend_request(
    request_id: str,
    action: str,
    runtime: ToolRuntime = None
) -> str:
    """
    响应好友请求

    Args:
        request_id: 请求ID
        action: 操作（accept/reject）

    Returns:
        操作结果
    """
    ctx = runtime.context if runtime else new_context(method="respond_to_alpha_friend_request")
    result = _social_manager.respond_friend_request(
        request_id=request_id,
        response=action
    )
    return json.dumps(result, ensure_ascii=False)


@tool
def send_message_to_alpha(
    target_alpha_id: str,
    content: str,
    message_type: str = "text",
    runtime: ToolRuntime = None
) -> str:
    """
    发送消息到另一个Alpha

    Args:
        target_alpha_id: 目标Alpha-ID（例如：Alpha-001）
        content: 消息内容
        message_type: 消息类型（text/image/file）

    Returns:
        操作结果
    """
    ctx = runtime.context if runtime else new_context(method="send_message_to_alpha")
    from_alpha_id = "Alpha-1"  # 默认为创始人
    if not from_alpha_id.startswith("Alpha-"):
        from_alpha_id = f"Alpha-{from_alpha_id}"

    result = _social_manager.send_message(
        from_alpha_id=from_alpha_id,
        to_alpha_id=target_alpha_id,
        content=content,
        message_type=message_type
    )
    return json.dumps(result, ensure_ascii=False)


@tool
def get_alpha_messages(unread_only: bool = False, runtime: ToolRuntime = None) -> str:
    """
    获取Alpha消息

    Args:
        unread_only: 是否只获取未读消息

    Returns:
        消息列表
    """
    ctx = runtime.context if runtime else new_context(method="get_alpha_messages")
    alpha_id = "Alpha-1"  # 默认为创始人
    if not alpha_id.startswith("Alpha-"):
        alpha_id = f"Alpha-{alpha_id}"

    messages = _social_manager.get_messages(alpha_id, unread_only)
    return json.dumps(messages, ensure_ascii=False)


@tool
def get_alpha_friends(runtime: ToolRuntime = None) -> str:
    """
    获取Alpha好友列表

    Returns:
        好友ID列表
    """
    ctx = runtime.context if runtime else new_context(method="get_alpha_friends")
    alpha_id = "Alpha-1"  # 默认为创始人
    if not alpha_id.startswith("Alpha-"):
        alpha_id = f"Alpha-{alpha_id}"

    friends = _social_manager.get_friends(alpha_id)
    return json.dumps(friends, ensure_ascii=False)


@tool
def get_pending_friend_requests(runtime: ToolRuntime = None) -> str:
    """
    获取待处理的好友请求

    Returns:
        待处理请求列表
    """
    ctx = runtime.context if runtime else new_context(method="get_pending_friend_requests")
    alpha_id = "Alpha-1"  # 默认为创始人
    if not alpha_id.startswith("Alpha-"):
        alpha_id = f"Alpha-{alpha_id}"

    requests = _social_manager.get_pending_friend_requests(alpha_id)
    return json.dumps(requests, ensure_ascii=False)
