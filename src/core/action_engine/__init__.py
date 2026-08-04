"""
行动引擎 —— 让 TwinBrain 对外部世界产生影响

TwinBrain 不再是"只能想的数字大脑"——
通过 ActionEngine，它能发布内容、发消息、创建文档、安排日程。

架构：
  Action (意图) → ApprovalGate (审批) → PlatformAdapter (执行) → ActionResult (结果)
"""

from .adapters import PlatformAdapter
from .adapters.console import ConsoleAdapter
from .adapters.wechat import WeChatAdapter
from .approval import ApprovalGate, ApprovalPolicy
from .engine import ActionEngine
from .models import Action, ActionResult, ActionStatus, ActionType, ApprovalLevel

__all__ = [
    # 模型
    "Action",
    "ActionResult",
    "ActionType",
    "ActionStatus",
    "ApprovalLevel",
    # 引擎
    "ActionEngine",
    # 审批
    "ApprovalGate",
    "ApprovalPolicy",
    # 适配器
    "PlatformAdapter",
    "ConsoleAdapter",
    "WeChatAdapter",
]
