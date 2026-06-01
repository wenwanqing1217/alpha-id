"""
平台适配器 —— 抽象所有外部平台的执行接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..models import Action, ActionResult


class PlatformAdapter(ABC):
    """
    平台适配器基类

    每个平台（微信、小红书、飞书等）继承此类，
    实现 execute 方法完成实际 API 调用。
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """平台标识：wechat, xiaohongshu, feishu, console"""
        ...

    @abstractmethod
    def execute(self, action: Action) -> ActionResult:
        """
        执行一个行动

        这是适配器的核心方法。
        接收标准化的 Action，返回标准化的 ActionResult。
        """
        ...

    def validate(self, action: Action) -> Optional[str]:
        """
        验证行动参数是否合法

        返回 None 表示合法，返回字符串表示错误原因。
        """
        return None

    def get_capabilities(self) -> Dict[str, Any]:
        """返回此平台支持的能力列表"""
        return {
            "platform": self.platform_name,
            "actions": [],
            "authenticated": False,
        }
