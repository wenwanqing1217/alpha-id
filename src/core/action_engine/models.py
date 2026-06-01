"""
行动引擎数据模型
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class ActionType(Enum):
    """行动类型"""

    POST = auto()  # 发布内容（朋友圈、小红书帖子等）
    REPLY = auto()  # 回复消息
    SEND_MESSAGE = auto()  # 发送私信
    SEND_IMAGE = auto()  # 发送图片
    SEND_FILE = auto()  # 发送文件
    SEND_LINK = auto()  # 发送链接卡片
    ADD_FRIEND = auto()  # 添加好友
    CREATE_GROUP = auto()  # 创建群聊
    GET_CONTACTS = auto()  # 获取联系人列表
    CREATE_DOC = auto()  # 创建文档
    SCHEDULE = auto()  # 创建日程/提醒
    EXECUTE = auto()  # 执行外部命令/API
    CUSTOM = auto()  # 自定义行动


class ActionStatus(Enum):
    """行动生命周期状态"""

    PENDING = auto()  # 刚创建，待审批
    APPROVED = auto()  # 已批准，待执行
    RUNNING = auto()  # 执行中
    SUCCESS = auto()  # 执行成功
    FAILED = auto()  # 执行失败
    REJECTED = auto()  # 被驳回
    CANCELLED = auto()  # 已取消
    RETRYING = auto()  # 重试中


class ApprovalLevel(Enum):
    """审批级别"""

    AUTO = auto()  # 自动批准（低风险行动）
    NOTIFY = auto()  # 自动执行，但通知用户
    CONFIRM = auto()  # 需要用户确认
    REVIEW = auto()  # 需要用户审查内容后确认
    BLOCK = auto()  # 永远阻止（高风险）


@dataclass
class ActionResult:
    """行动执行结果"""

    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    platform_response: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    executed_at: float = field(default_factory=lambda: datetime.now().timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Action:
    """
    一个待执行的行动

    这是 TwinBrain 对外部世界产生影响的原子单元。
    与 Message 不同——Message 是数字实体间的通信，
    Action 是向真实世界（平台、API）发起的操作。
    """

    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    action_type: ActionType = ActionType.CUSTOM
    platform: str = ""  # 目标平台：wechat, xiaohongshu, feishu, console
    intent: str = ""  # 自然语言描述：帮我把这篇发小红书
    payload: Dict[str, Any] = field(default_factory=dict)  # 行动参数
    status: ActionStatus = ActionStatus.PENDING
    approval_level: ApprovalLevel = ApprovalLevel.AUTO
    source_alpha_id: str = ""  # 发起者
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    scheduled_at: Optional[float] = None  # 预约执行时间
    result: Optional[ActionResult] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["action_type"] = self.action_type.name
        d["status"] = self.status.name
        d["approval_level"] = self.approval_level.name
        if self.result:
            d["result"] = self.result.to_dict()
        return d

    def approve(self) -> None:
        self.status = ActionStatus.APPROVED

    def reject(self, reason: str = "") -> None:
        self.status = ActionStatus.REJECTED
        self.metadata["reject_reason"] = reason

    def cancel(self) -> None:
        self.status = ActionStatus.CANCELLED

    def mark_running(self) -> None:
        self.status = ActionStatus.RUNNING

    def mark_done(self, result: ActionResult) -> None:
        self.result = result
        self.status = ActionStatus.SUCCESS if result.success else ActionStatus.FAILED

    @classmethod
    def create_post(
        cls, platform: str, content: str, images: Optional[List[str]] = None, source_alpha_id: str = ""
    ) -> "Action":
        """快捷创建发布行动"""
        return cls(
            action_type=ActionType.POST,
            platform=platform,
            intent=f"在{platform}发布内容",
            payload={
                "content": content,
                "images": images or [],
                "title": "",
                "tags": [],
                "visibility": "public",
            },
            source_alpha_id=source_alpha_id,
            tags=["post"],
        )

    @classmethod
    def create_message(cls, platform: str, recipient: str, content: str, source_alpha_id: str = "") -> "Action":
        """快捷创建发送消息行动"""
        return cls(
            action_type=ActionType.SEND_MESSAGE,
            platform=platform,
            intent=f"在{platform}发送消息给{recipient}",
            payload={
                "recipient": recipient,
                "content": content,
            },
            source_alpha_id=source_alpha_id,
            tags=["message"],
        )
