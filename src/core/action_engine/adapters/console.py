"""
Console 适配器 —— 开发调试用的"假执行"
所有行动只打印日志，不真的调用外部 API
"""

from typing import Any, Dict, Optional
from datetime import datetime
from . import PlatformAdapter
from ..models import Action, ActionResult, ActionType


class ConsoleAdapter(PlatformAdapter):
    """
    控制台适配器：所有行动只输出日志，不做真实调用。
    用于开发阶段验证行动引擎流程。
    """

    @property
    def platform_name(self) -> str:
        return "console"

    def execute(self, action: Action) -> ActionResult:
        print(f"[ActionEngine][{self.platform_name}] 执行: {action.intent}")
        print(f"  类型: {action.action_type.name}")
        print(f"  参数: {action.payload}")

        # 模拟执行
        if action.action_type == ActionType.POST:
            content = action.payload.get("content", "")
            print(f"  [模拟发布] 内容({len(content)}字): {content[:80]}...")
        elif action.action_type == ActionType.SEND_MESSAGE:
            print(f"  [模拟消息] 发给 {action.payload.get('recipient', 'unknown')}")
        elif action.action_type == ActionType.SEND_IMAGE:
            print(f"  [模拟图片] 发给 {action.payload.get('target', 'unknown')}")
        elif action.action_type == ActionType.SEND_FILE:
            print(f"  [模拟文件] 发给 {action.payload.get('target', 'unknown')}")
        elif action.action_type == ActionType.SEND_LINK:
            print(f"  [模拟链接] {action.payload.get('title', '无标题')}")
        elif action.action_type == ActionType.ADD_FRIEND:
            print(f"  [模拟加好友] {action.payload.get('wxid', 'unknown')}")
        elif action.action_type == ActionType.CREATE_GROUP:
            print(f"  [模拟建群] {action.payload.get('group_name', '未命名群')}")
        elif action.action_type == ActionType.GET_CONTACTS:
            print(f"  [模拟获取联系人] 返回模拟联系人列表")
        elif action.action_type == ActionType.CREATE_DOC:
            print(f"  [模拟创建文档] 标题: {action.payload.get('title', '未命名')}")
        elif action.action_type == ActionType.SCHEDULE:
            print(f"  [模拟创建日程] 标题: {action.payload.get('title', '未命名')}")

        return ActionResult(
            success=True,
            message=f"[Console] {action.intent} 已模拟执行",
            data={"platform": "console", "simulated": True},
            executed_at=datetime.now().timestamp(),
        )

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "platform": "console",
            "actions": [t.name for t in ActionType],
            "authenticated": True,
            "note": "Development/debug adapter — no real API calls",
        }
