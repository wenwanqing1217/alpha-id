# TERM: Agent — Alpha-ID SDK 一站式入口（TwinBrain + AgentLoop + ChannelAdapter 统一接口）
"""
Alpha-ID Agent — SDK 一站式入口

使用方式：
    from alpha_id import Agent

    agent = Agent()
    agent.identify("my-device-fp")   # 注册 + 登录，绑定身份
    agent.connect("Alpha-002")       # 加好友
    agent.think("来聊天吧")          # TwinBrain 自主思考
"""

from typing import Any, Dict, List, Optional

from alpha_id.container import Container
from core.twin_brain import TwinBrain


class Agent:
    """Alpha-ID Agent — 有身份、有社交、有风控、有大脑的 AI 实体"""

    def __init__(self, storage=None):
        """
        Args:
            storage: 可选的存储后端（默认 SQLite），测试时可注入 mock
        """
        self._container = Container.instance()
        if storage is not None:
            self._container.storage = storage

        self._alpha_id: Optional[str] = None
        self._brain: Optional[TwinBrain] = None

    # ── 身份 ──

    @property
    def alpha_id(self) -> Optional[str]:
        return self._alpha_id

    @property
    def brain(self) -> Optional[TwinBrain]:
        return self._brain

    def register(self, device_fingerprint: str, **kwargs) -> Dict[str, Any]:
        """注册新身份"""
        result = self._container.identity.register_user(
            device_fingerprint=device_fingerprint,
            **kwargs,
        )
        if result.get("success"):
            self._alpha_id = result["alpha_id"]
        return result

    def login(self, alpha_id: str, device_fingerprint: str) -> bool:
        """登录到已有身份"""
        profile = self._container.identity.get_user_profile(alpha_id)
        if profile is None:
            return False
        devices = profile.get("devices", [])
        if devices and device_fingerprint not in devices:
            # 尝试绑定新设备
            self._container.identity.update_device_binding(alpha_id, device_fingerprint)
        self._alpha_id = alpha_id
        return True

    def identify(self, device_fingerprint: str) -> Dict[str, Any]:
        """一键注册或登录"""
        # 尝试找已有用户
        all_users = self._container.storage.load("users") or {}
        for aid, data in all_users.items():
            devices = data.get("devices", [])
            if device_fingerprint in devices:
                self._alpha_id = aid
                return {"success": True, "action": "login", "alpha_id": aid}
        # 没有就注册
        return self.register(device_fingerprint)

    def get_profile(self) -> Optional[Dict[str, Any]]:
        if not self._alpha_id:
            return None
        return self._container.identity.get_user_profile(self._alpha_id)

    # ── 社交 ──

    def connect(self, target_alpha_id: str, message: str = "你好，交个朋友吧") -> Dict[str, Any]:
        """发送好友请求"""
        return self._container.social.send_friend_request(
            from_alpha_id=self._alpha_id,
            to_alpha_id=target_alpha_id,
            message=message,
        )

    def accept_request(self, request_id: str) -> Dict[str, Any]:
        """接受好友请求"""
        return self._container.social.respond_friend_request(request_id=request_id, response="accept")

    def reject_request(self, request_id: str) -> Dict[str, Any]:
        """拒绝好友请求"""
        return self._container.social.respond_friend_request(request_id=request_id, response="reject")

    def friends(self) -> List[str]:
        """获取好友列表"""
        if not self._alpha_id:
            return []
        return self._container.social.get_friends(self._alpha_id)

    def send_message(self, to_alpha_id: str, content: str, message_type: str = "text") -> Dict[str, Any]:
        """发送消息"""
        return self._container.social.send_message(
            from_alpha_id=self._alpha_id,
            to_alpha_id=to_alpha_id,
            content=content,
            message_type=message_type,
        )

    def messages(self, unread_only: bool = False) -> List[Dict[str, Any]]:
        """获取消息"""
        if not self._alpha_id:
            return []
        return self._container.social.get_messages(self._alpha_id, unread_only=unread_only)

    def pending_requests(self) -> List[Dict[str, Any]]:
        """获取待处理的好友请求"""
        if not self._alpha_id:
            return []
        return self._container.social.get_pending_friend_requests(self._alpha_id)

    # ── 大脑 ──

    def think(self, input_text: str = "") -> Dict[str, Any]:
        """初始化大脑（如果需要）并思考"""
        if not self._alpha_id:
            return {"success": False, "message": "请先注册或登录"}

        from core.message import Message

        if self._brain is None:
            from core.twin_brain import BrainRegistry

            registry = BrainRegistry()
            self._brain = registry.get_or_create(self._alpha_id, storage=self._container.storage)

        # awake → think cycle
        self._brain.awake()

        msg = Message(
            sender=self._alpha_id,
            recipient=self._alpha_id,
            msg_type="chat",
            payload={"text": input_text} if input_text else {},
        )
        response = self._brain.receive(msg)
        think_result = self._brain.think()
        return {
            "success": True,
            "response": response.to_dict() if hasattr(response, "to_dict") else str(response),
            "think": think_result,
            "state": self._brain.state.value,
        }

    # ── 风控 ──

    def evaluate_risk(
        self,
        device_info: Optional[Dict] = None,
        behavior_info: Optional[Dict] = None,
        voice_info: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """评估当前风险"""
        engine = self._container.risk
        device_score = engine.calculate_device_score(
            self._make_device_fp(device_info) if device_info else None,
            None,
        )
        behavior_score = (
            engine.calculate_behavior_score(
                self._make_behavior_fp(behavior_info),
            )
            if behavior_info
            else 50.0
        )
        voice_score = engine.calculate_voice_score(voice_info)
        total = engine.calculate_total_risk(device_score, behavior_score, voice_score)
        level = engine.determine_risk_level(total)
        return {
            "risk_score": round(total, 2),
            "risk_level": level,
            "device_score": device_score,
            "behavior_score": behavior_score,
            "voice_score": voice_score,
        }

    @staticmethod
    def _make_device_fp(info: Dict):
        from core.risk_engine import DeviceFingerprint

        return DeviceFingerprint(
            hardware_id=info.get("hardware_id", ""),
            ip_address=info.get("ip_address", ""),
            location=info.get("location", ""),
            browser_info=info.get("browser_info", ""),
            first_access_time=info.get("first_access_time", ""),
            screen_resolution=info.get("screen_resolution", ""),
        )

    @staticmethod
    def _make_behavior_fp(info: Dict):
        from core.risk_engine import BehaviorFingerprint

        return BehaviorFingerprint(
            typing_speed=info.get("typing_speed", 0.0),
            mouse_movement=info.get("mouse_movement", 0.0),
            session_time=info.get("session_time", ""),
            input_pattern=info.get("input_pattern", ""),
            language=info.get("language", ""),
        )
