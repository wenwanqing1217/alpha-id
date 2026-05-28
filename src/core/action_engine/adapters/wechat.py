"""
微信适配器 —— TwinBrain 的微信执行层

架构说明
═════════════════════════════════════════
WeChatAdapter 不直接操作微信协议，而是通过一个可插拔的 "后端" (Backend)
来执行实际操作。这有 3 个好处：

1. 解耦：适配器逻辑（参数校验、权限、格式化）与通讯逻辑分离
2. 可替换：itchat / WeChatFerry / UIAutomation 可随时切换
3. 可降级：无真实后端时自动进入模拟模式，不影响开发

当前内置后端
─────────────────────────────────
- SimulationBackend  (默认) 只打日志，不操作微信
- WcfBackend         (可选) 基于 WeChatFerry 的 gRPC 接口
                      安装: pip install wcf-python
- ItchatBackend      (可选) 基于 itchat 的 Web 协议
                      安装: pip install itchat-uos

使用方法
─────────────────────────────────
    adapter = WeChatAdapter(backend=WcfBackend())
    adapter = WeChatAdapter()  # 自动使用 SimulationBackend
═════════════════════════════════════════
"""

from typing import Any, Dict, List, Optional, Set
from datetime import datetime
from abc import ABC, abstractmethod

from . import PlatformAdapter
from ..models import Action, ActionResult, ActionType


# ═══════════════════════════════════════
# 后端抽象
# ═══════════════════════════════════════

class WeChatBackend(ABC):
    """微信操作后端的抽象接口"""

    @abstractmethod
    def is_available(self) -> bool:
        """检查后端是否可用（微信是否登录、API 是否连通）"""
        ...

    @abstractmethod
    def get_self_info(self) -> Dict[str, Any]:
        """返回当前微信账号信息"""
        ...

    @abstractmethod
    def get_contacts(self) -> List[Dict[str, Any]]:
        """获取联系人列表"""
        ...

    @abstractmethod
    def send_text(self, target: str, text: str) -> bool:
        """发送文本消息给指定联系人/群"""
        ...

    @abstractmethod
    def send_image(self, target: str, image_path: str) -> bool:
        """发送图片"""
        ...

    @abstractmethod
    def send_file(self, target: str, file_path: str) -> bool:
        """发送文件"""
        ...

    @abstractmethod
    def send_link(self, target: str, title: str, desc: str, url: str, cover_url: str = "") -> bool:
        """发送链接卡片"""
        ...

    @abstractmethod
    def add_friend(self, wx_id: str, message: str) -> bool:
        """添加好友"""
        ...

    @abstractmethod
    def create_group(self, members: List[str], group_name: str = "") -> bool:
        """创建群聊"""
        ...


# ═══════════════════════════════════════
# 模拟后端（开发调试用）
# ═══════════════════════════════════════

class SimulationBackend(WeChatBackend):
    """模拟后端 — 不操作真实微信，只打日志"""

    def is_available(self) -> bool:
        return True  # 模拟模式永远"可用"

    def get_self_info(self) -> Dict[str, Any]:
        return {
            "nickname": "TwinBrain(模拟)",
            "wxid": "simulated_wechat",
            "available": True,
        }

    def get_contacts(self) -> List[Dict[str, Any]]:
        return [
            {"nickname": "张三(模拟)", "wxid": "zhangsan_sim"},
            {"nickname": "李四(模拟)", "wxid": "lisi_sim"},
            {"nickname": "工作群(模拟)", "wxid": "work_group_sim", "is_group": True},
        ]

    def send_text(self, target: str, text: str) -> bool:
        print(f"[WeChat-Sim] 发送文本 → {target}: {text[:60]}...")
        return True

    def send_image(self, target: str, image_path: str) -> bool:
        print(f"[WeChat-Sim] 发送图片 → {target}: {image_path}")
        return True

    def send_file(self, target: str, file_path: str) -> bool:
        print(f"[WeChat-Sim] 发送文件 → {target}: {file_path}")
        return True

    def send_link(self, target: str, title: str, desc: str, url: str, cover_url: str = "") -> bool:
        print(f"[WeChat-Sim] 发送链接 → {target}: {title} ({url})")
        return True

    def add_friend(self, wx_id: str, message: str) -> bool:
        print(f"[WeChat-Sim] 添加好友: {wx_id} 附言: {message}")
        return True

    def create_group(self, members: List[str], group_name: str) -> bool:
        print(f"[WeChat-Sim] 创建群聊: {group_name}, 成员: {members}")
        return True


# ═══════════════════════════════════════
# WeChatFerry 后端（真实微信）
# ═══════════════════════════════════════

class WcfBackend(WeChatBackend):
    """
    WeChatFerry 后端 (wcferry)

    通过 Windows 微信客户端的 DLL 注入接口操作微信。
    要求：
    1. Windows 系统
    2. 微信 PC 客户端已登录 (3.9.x 版本)
    3. pip install wcferry

    注意：PyPI 上的 wcf 包是 WCF 二进制 XML 解析器（不相关），
    正确的 WeChatFerry 包名是 wcferry。
    """

    def __init__(self):
        self._wcf = None
        self._initialize()

    def _initialize(self) -> None:
        try:
            from wcferry import Wcf
            self._wcf = Wcf()
        except ImportError:
            print("[WeChat-Wcf] wcferry 未安装，请运行: pip install wcferry")
        except Exception as e:
            print(f"[WeChat-Wcf] 初始化失败: {e}")

    def is_available(self) -> bool:
        try:
            return self._wcf is not None and self._wcf.is_login()
        except Exception:
            return False

    def get_self_info(self) -> Dict[str, Any]:
        if not self._wcf:
            return {}
        info = self._wcf.get_user_info()
        return {
            "nickname": info.get("name", ""),
            "wxid": info.get("wxid", ""),
            "phone": info.get("phone", ""),
            "available": self.is_available(),
        }

    def get_contacts(self) -> List[Dict[str, Any]]:
        if not self._wcf:
            return []
        contacts = self._wcf.get_contacts()
        return [
            {
                "nickname": c.get("name", ""),
                "wxid": c.get("wxid", ""),
                "remark": c.get("remark", ""),
            }
            for c in contacts
        ]

    def send_text(self, target: str, text: str) -> bool:
        if not self._wcf:
            return False
        try:
            self._wcf.send_text(target, text)
            return True
        except Exception as e:
            print(f"[WeChat-Wcf] 发送文本失败: {e}")
            return False

    def send_image(self, target: str, image_path: str) -> bool:
        if not self._wcf:
            return False
        try:
            self._wcf.send_image(target, image_path)
            return True
        except Exception as e:
            print(f"[WeChat-Wcf] 发送图片失败: {e}")
            return False

    def send_file(self, target: str, file_path: str) -> bool:
        if not self._wcf:
            return False
        try:
            self._wcf.send_file(target, file_path)
            return True
        except Exception as e:
            print(f"[WeChat-Wcf] 发送文件失败: {e}")
            return False

    def send_link(self, target: str, title: str, desc: str, url: str, cover_url: str = "") -> bool:
        if not self._wcf:
            return False
        try:
            self._wcf.send_link(target, title, desc, url, cover_url)
            return True
        except Exception as e:
            print(f"[WeChat-Wcf] 发送链接失败: {e}")
            return False

    def add_friend(self, wx_id: str, message: str) -> bool:
        print("[WeChat-Wcf] WeChatFerry 不支持添加好友操作")
        return False

    def create_group(self, members: List[str], group_name: str = "") -> bool:
        if not self._wcf or not members:
            return False
        try:
            # WeChatFerry 通过邀请方式创建群
            self._wcf.create_chatroom(members)
            return True
        except Exception as e:
            print(f"[WeChat-Wcf] 建群失败: {e}")
            return False


# ═══════════════════════════════════════
# 适配器本身
# ═══════════════════════════════════════

class WeChatAdapter(PlatformAdapter):
    """
    微信适配器

    支持的行动：
    - SEND_MESSAGE      发送文本消息
    - SEND_IMAGE        发送图片
    - SEND_FILE         发送文件
    - SEND_LINK         发送链接卡片
    - REPLY             回复消息
    - ADD_FRIEND        添加好友
    - CREATE_GROUP      创建群聊
    - GET_CONTACTS      获取联系人列表
    """

    def __init__(self, backend: Optional[WeChatBackend] = None, simulate: bool = True):
        """
        Args:
            backend: 微信操作后端。为 None 时根据 simulate 参数决定：
                     - simulate=True  → SimulationBackend
                     - simulate=False → WcfBackend (要求 wcf-python)
            simulate: 是否强制使用模拟模式
        """
        if backend is not None:
            self._backend = backend
        elif simulate:
            self._backend = SimulationBackend()
        else:
            self._backend = WcfBackend()

    @property
    def platform_name(self) -> str:
        return "wechat"

    @property
    def backend(self) -> WeChatBackend:
        return self._backend

    def execute(self, action: Action) -> ActionResult:
        action_type = action.action_type
        payload = action.payload or {}

        target = payload.get("target", "")
        content = payload.get("content", "")

        try:
            if action_type == ActionType.SEND_MESSAGE:
                success = self._backend.send_text(target, content)
                return self._result(success, "发送文本", {
                    "target": target, "length": len(content),
                })

            elif action_type == ActionType.REPLY:
                success = self._backend.send_text(target, content)
                return self._result(success, "回复消息", {
                    "target": target, "reply_to": payload.get("reply_to", ""),
                })

            elif action_type == ActionType.SEND_IMAGE:
                image_path = payload.get("image_path", content)
                success = self._backend.send_image(target, image_path)
                return self._result(success, "发送图片", {
                    "target": target, "image_path": image_path,
                })

            elif action_type == ActionType.SEND_FILE:
                file_path = payload.get("file_path", content)
                success = self._backend.send_file(target, file_path)
                return self._result(success, "发送文件", {
                    "target": target, "file_path": file_path,
                })

            elif action_type == ActionType.SEND_LINK:
                success = self._backend.send_link(
                    target=target,
                    title=payload.get("title", ""),
                    desc=payload.get("description", ""),
                    url=payload.get("url", ""),
                    cover_url=payload.get("cover_url", ""),
                )
                return self._result(success, "发送链接", {
                    "target": target,
                    "title": payload.get("title", ""),
                })

            elif action_type == ActionType.ADD_FRIEND:
                success = self._backend.add_friend(
                    wx_id=payload.get("wxid", content),
                    message=payload.get("message", "你好，我是TwinBrain"),
                )
                return self._result(success, "添加好友", {
                    "wxid": payload.get("wxid", content),
                })

            elif action_type == ActionType.CREATE_GROUP:
                members = payload.get("members", [])
                success = self._backend.create_group(
                    members=members,
                    group_name=payload.get("group_name", ""),
                )
                return self._result(success, "创建群聊", {
                    "member_count": len(members),
                })

            elif action_type == ActionType.GET_CONTACTS:
                contacts = self._backend.get_contacts()
                return ActionResult(
                    success=True,
                    message=f"获取到 {len(contacts)} 个联系人",
                    data={"contacts": contacts, "count": len(contacts)},
                    executed_at=datetime.now().timestamp(),
                )

            else:
                return ActionResult(
                    success=False,
                    message=f"微信适配器不支持操作: {action_type.name}",
                    error_code="UNSUPPORTED_ACTION",
                )

        except Exception as e:
            return ActionResult(
                success=False,
                message=f"微信执行异常: {str(e)}",
                error_code="WECHAT_ERROR",
                executed_at=datetime.now().timestamp(),
            )

    def validate(self, action: Action) -> Optional[str]:
        """行动参数校验"""
        action_type = action.action_type
        payload = action.payload or {}

        if action_type == ActionType.SEND_MESSAGE:
            if not payload.get("target") and not payload.get("content"):
                return "发送消息需要 target(目标) 和 content(内容)"

        elif action_type == ActionType.SEND_IMAGE:
            if not payload.get("target"):
                return "发送图片需要 target(目标)"
            if not payload.get("image_path") and not payload.get("content"):
                return "发送图片需要 image_path 或 content(路径)"

        elif action_type == ActionType.SEND_LINK:
            if not payload.get("url"):
                return "发送链接需要 url"

        elif action_type == ActionType.ADD_FRIEND:
            if not payload.get("wxid") and not payload.get("content"):
                return "添加好友需要 wxid"

        elif action_type == ActionType.CREATE_GROUP:
            members = payload.get("members", [])
            if not isinstance(members, list) or len(members) < 2:
                return "创建群聊至少需要 2 个成员"

        return None

    def get_capabilities(self) -> Dict[str, Any]:
        available = self._backend.is_available()
        info = self._backend.get_self_info()
        return {
            "platform": "wechat",
            "authenticated": available,
            "backend_type": type(self._backend).__name__,
            "account": info.get("nickname", "未登录"),
            "actions": [
                "SEND_MESSAGE",
                "SEND_IMAGE",
                "SEND_FILE",
                "SEND_LINK",
                "REPLY",
                "ADD_FRIEND",
                "CREATE_GROUP",
                "GET_CONTACTS",
            ],
            "note": "真实模式需微信 PC 客户端登录 + wcf-python",
        }

    # ── 内部 ──

    def _result(self, success: bool, action_name: str, extra: Dict[str, Any] = None) -> ActionResult:
        status = "成功" if success else "失败"
        return ActionResult(
            success=success,
            message=f"[微信] {action_name}{status}",
            data=extra or {},
            executed_at=datetime.now().timestamp(),
        )
