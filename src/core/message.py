"""
Alpha-ID 通信协议 —— 数字实体间的统一消息格式

所有 Alpha-ID 之间的通信（消息、好友请求、状态查询等）
都走同一通道，外部应用（电子宠物等）也通过此协议接入。
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

# ── 消息类型枚举 ──


class MessageType:
    """消息类型常量"""

    # 社交
    CHAT = "chat"  # 普通聊天消息
    FRIEND_REQUEST = "friend_request"  # 好友请求
    FRIEND_RESPONSE = "friend_response"  # 好友请求回复
    # 查询
    PROFILE_QUERY = "profile_query"  # 查询对方档案
    PROFILE_REPLY = "profile_reply"  # 档案回复
    STATUS_QUERY = "status_query"  # 查询在线状态
    STATUS_REPLY = "status_reply"  # 状态回复
    # 系统
    PING = "ping"  # 心跳
    PONG = "pong"  # 心跳回复
    ERROR = "error"  # 错误
    # 外部应用
    APP_ACTION = "app_action"  # 外部应用动作（电子宠物等）
    # 行动引擎
    ACTION_CONFIRM = "action_confirm"  # 行动审批回应
    ACTION_QUERY = "action_query"  # 行动状态查询


@dataclass
class Message:
    """统一消息格式"""

    version: str = "2.0"
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    sender: str = ""  # 来源 Alpha-ID
    recipient: str = ""  # 目标 Alpha-ID
    msg_type: str = MessageType.CHAT  # 消息类型
    payload: Dict[str, Any] = field(default_factory=dict)  # 具体内容
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    signature: Optional[str] = None  # 未来：数字签名

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def create_chat(cls, sender: str, recipient: str, text: str) -> "Message":
        return cls(sender=sender, recipient=recipient, msg_type=MessageType.CHAT, payload={"text": text})

    @classmethod
    def create_friend_request(cls, sender: str, recipient: str, note: str = "") -> "Message":
        return cls(sender=sender, recipient=recipient, msg_type=MessageType.FRIEND_REQUEST, payload={"note": note})

    @classmethod
    def create_profile_query(cls, sender: str, target: str, layer: str = "public") -> "Message":
        return cls(sender=sender, recipient=target, msg_type=MessageType.PROFILE_QUERY, payload={"layer": layer})


# ── 响应格式 ──


@dataclass
class Response:
    """统一响应格式"""

    success: bool = True
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def ok(cls, data: Dict[str, Any] = None, message: str = "ok") -> "Response":
        return cls(success=True, message=message, data=data or {})

    @classmethod
    def fail(cls, message: str, error_code: str = "UNKNOWN") -> "Response":
        return cls(success=False, message=message, error_code=error_code)
