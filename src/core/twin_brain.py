"""
Alpha-ID 孪生大脑 —— 数字实体的核心运行时

每个 Alpha-ID 在系统中被激活后，持有一个 TwinBrain 实例。
大脑统一管理身份、记忆、社交、风控，并对外提供通信接口。
"""

import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field, asdict


# ── 大脑状态枚举 ──

class BrainState(Enum):
    """孪生大脑运行状态"""
    SLEEP = "sleep"       # 休眠/离线
    IDLE = "idle"         # 空闲待机（低功耗）
    AWAKE = "awake"       # 活跃（处理中）
    ERROR = "error"       # 异常（安全模式）


# ── 状态转换规则 ──

BRAIN_TRANSITIONS: Dict[BrainState, List[BrainState]] = {
    BrainState.SLEEP: [BrainState.IDLE, BrainState.AWAKE, BrainState.ERROR],
    BrainState.IDLE:  [BrainState.AWAKE, BrainState.SLEEP, BrainState.ERROR],
    BrainState.AWAKE: [BrainState.IDLE, BrainState.SLEEP, BrainState.ERROR],
    BrainState.ERROR: [BrainState.SLEEP, BrainState.IDLE],
}


def can_transition(from_state: BrainState, to_state: BrainState) -> bool:
    """检查状态转换是否合法"""
    return to_state in BRAIN_TRANSITIONS.get(from_state, [])


# ── 可见度模型 ──

class VisibilityLayer(Enum):
    """对外可见度层级"""
    PUBLIC = "public"      # 任何人可见
    FRIENDS = "friends"    # 好友可见
    CLOSE = "close"        # 密友可见
    SELF = "self"          # 仅自己可见


# ── 大脑设置 ──

@dataclass
class BrainSettings:
    """孪生大脑自主行为设置"""
    auto_reply: bool = False            # 离线时自动回复
    auto_reply_text: str = "我现在无法处理，稍后回复你。"
    wake_hours_start: int = 8           # 唤醒时间（小时）
    wake_hours_end: int = 22            # 休眠时间（小时）
    idle_timeout: int = 300             # 空闲超时（秒），默认 5 分钟转入 idle
    sleep_timeout: int = 1800           # 待机超时（秒），默认 30 分钟转入 sleep
    auto_actions: List[Dict] = field(default_factory=list)  # 定时/条件触发的自主行为


# ── 核心大脑类 ──

class TwinBrain:
    """
    孪生大脑 —— 每个 Alpha-ID 持有一个实例。

    用法：
        brain = TwinBrain(alpha_id="Alpha-001", storage=...)
        brain.awake()                        # 唤醒大脑
        response = brain.receive(msg)         # 处理消息
        brain.think()                         # 自主学习周期
        brain.sleep()                         # 休眠
    """

    def __init__(
        self,
        alpha_id: str,
        storage=None,         # StorageBackend 实例
        settings: Optional[BrainSettings] = None,
    ):
        self.alpha_id = alpha_id
        self.state = BrainState.SLEEP
        self.settings = settings or BrainSettings()
        self._storage = storage

        # 子模块（惰性初始化）
        self._identity = None    # IdentityManager
        self._social = None      # SocialManager
        self._risk = None        # RiskEngine
        self._memory = None      # MemoryStore
        self._actions = None     # ActionEngine

        # 运行时数据
        self.last_active_time = 0.0
        self.active_since = 0.0
        self.error_log: List[Dict] = []
        self._message_count = 0

    # ── 属性 ──

    @property
    def identity(self):
        """身份管理器（惰性加载）"""
        if self._identity is None:
            from core.user_identity import UserIdentityManager
            self._identity = UserIdentityManager(storage=self._storage)
        return self._identity

    @property
    def social(self):
        """社交管理器（惰性加载）"""
        if self._social is None:
            from core.alpha_social import AlphaSocialManager
            self._social = AlphaSocialManager(storage=self._storage)
        return self._social

    @property
    def risk(self):
        """风控引擎（惰性加载）"""
        if self._risk is None:
            from core.risk_engine import RiskAssessmentEngine
            self._risk = RiskAssessmentEngine()
        return self._risk

    @property
    def memory(self):
        """记忆存储器（惰性加载）"""
        if self._memory is None:
            from core.memory_store import MemoryStore
            self._memory = MemoryStore(alpha_id=self.alpha_id, storage=self._storage)
        return self._memory

    @property
    def actions(self):
        """行动引擎（惰性加载）"""
        if self._actions is None:
            from core.action_engine import ActionEngine, ConsoleAdapter
            self._actions = ActionEngine(alpha_id=self.alpha_id)
            self._actions.register_adapter(ConsoleAdapter())
        return self._actions

    # ── 状态管理 ──

    def transition_to(self, new_state: BrainState) -> bool:
        """安全地转换大脑状态"""
        if new_state == self.state:
            return True
        if not can_transition(self.state, new_state):
            self._log_error(f"非法状态转换: {self.state.value} -> {new_state.value}")
            return False

        old_state = self.state
        self.state = new_state

        if new_state == BrainState.AWAKE:
            self.active_since = time.time()
        if new_state == BrainState.SLEEP:
            self.active_since = 0.0

        self.last_active_time = time.time()
        return True

    def awake(self) -> bool:
        """唤醒大脑"""
        return self.transition_to(BrainState.AWAKE)

    def sleep(self) -> bool:
        """让大脑休眠"""
        return self.transition_to(BrainState.SLEEP)

    def idle(self) -> bool:
        """切换至空闲待机"""
        return self.transition_to(BrainState.IDLE)

    def is_active(self) -> bool:
        """大脑是否处于可处理消息的状态"""
        return self.state in (BrainState.AWAKE, BrainState.IDLE)

    # ── 核心方法 ──

    def receive(self, message: "Message") -> "Response":
        """
        接收并处理外部消息。

        对外部应用的统一入口。消息类型决定了路由：
        - chat / friend_request → 社交模块
        - profile_query → 身份模块
        - ping → 心跳回复
        """
        from core.message import Message, Response, MessageType

        if self.state == BrainState.SLEEP:
            if self.settings.auto_reply:
                return Response.ok(
                    data={"auto_reply": True},
                    message=self.settings.auto_reply_text
                )
            return Response.fail("该 Alpha-ID 当前不在线", error_code="SLEEPING")

        if self.state == BrainState.ERROR:
            return Response.fail("该 Alpha-ID 当前异常，请稍后再试", error_code="ERROR")

        self._message_count += 1
        self.last_active_time = time.time()

        # 按消息类型路由
        msg_type = message.msg_type

        if msg_type == MessageType.CHAT:
            return self._handle_chat(message)
        elif msg_type == MessageType.FRIEND_REQUEST:
            return self._handle_friend_request(message)
        elif msg_type == MessageType.FRIEND_RESPONSE:
            return self._handle_friend_response(message)
        elif msg_type == MessageType.PROFILE_QUERY:
            return self._handle_profile_query(message)
        elif msg_type == MessageType.PING:
            return Response.ok(data={
                "alpha_id": self.alpha_id,
                "status": self.state.value,
                "active_since": self.active_since,
            })
        elif msg_type == MessageType.ACTION_CONFIRM:
            return self._handle_action_confirm(message)
        elif msg_type == MessageType.ACTION_QUERY:
            return self._handle_action_query(message)
        elif msg_type == MessageType.APP_ACTION:
            return self._handle_app_action(message)
        else:
            return Response.fail(f"不支持的消息类型: {msg_type}", error_code="UNSUPPORTED_TYPE")

    # ── 行动引擎处理器 ──

    def _handle_action_confirm(self, message) -> "Response":
        """处理行动审批回应"""
        from core.message import Response

        if not self._actions:
            return Response.fail("行动引擎未初始化", error_code="NO_ACTION_ENGINE")

        action_id = message.payload.get("action_id", "")
        approved = message.payload.get("approved", False)
        note = message.payload.get("note", "")

        if not action_id:
            return Response.fail("缺少 action_id", error_code="MISSING_ACTION_ID")

        action = self.actions.confirm(action_id, approved=approved, note=note)
        if action is None:
            return Response.fail(f"未找到待审批的行动: {action_id}", error_code="ACTION_NOT_FOUND")

        # 如果批准了，立即执行
        if approved:
            action = self.actions.execute(action_id)
            if action and action.result:
                return Response.ok(
                    data=action.to_dict(),
                    message=f"行动 {action_id} 已执行: {action.result.message}"
                )

        return Response.ok(
            data=action.to_dict(),
            message=f"审批回应已处理: {'批准' if approved else '驳回'}"
        )

    def _handle_action_query(self, message) -> "Response":
        """查询行动状态"""
        from core.message import Response

        if not self._actions:
            return Response.fail("行动引擎未初始化", error_code="NO_ACTION_ENGINE")

        action_id = message.payload.get("action_id", "")
        if action_id:
            result = self.actions.get_action(action_id)
            if not result:
                return Response.fail(f"行动不存在: {action_id}", error_code="ACTION_NOT_FOUND")
            return Response.ok(data=result)

        # 返回概要
        return Response.ok(data={
            "stats": self.actions.get_stats(),
            "pending_approvals": self.actions.list_pending_approvals(),
        })

    def think(self) -> Dict[str, Any]:
        """
        自主学习周期：
        - 整理记忆（未来）
        - 检查待办好友请求
        - 检查并执行待办行动
        - 更新状态
        """
        results = {
            "alpha_id": self.alpha_id,
            "state": self.state.value,
            "message_count": self._message_count,
            "pending_requests": 0,
            "actions_taken": [],
            "action_stats": {},
        }

        # 检查是否有未处理的好友请求
        if self._social:
            requests = self.social.get_pending_requests(self.alpha_id)
            results["pending_requests"] = len(requests)

        # 检查并执行待处理的自动行动
        if self._actions:
            stats = self.actions.get_stats()
            results["action_stats"] = stats

            # idle 状态下执行待办的自动行动
            if self.state in (BrainState.IDLE, BrainState.AWAKE):
                pending = self.actions.get_pending_actions()
                for action in pending[:]:  # 拷贝遍历
                    executed = self.actions.execute(action.action_id)
                    if executed:
                        results["actions_taken"].append(f"action:{action.action_id}")
                        # 将执行结果写入记忆
                        if executed.result and executed.result.success and self._memory:
                            self.memory.save(
                                content=f"[自动行动] {executed.intent} - {executed.result.message}",
                                tags=["action", executed.platform, executed.action_type.name.lower()],
                                sensitivity=10,
                            )

        # 检查是否需要转 idle/sleep
        now = time.time()
        if self.state == BrainState.AWAKE and (now - self.last_active_time) > self.settings.idle_timeout:
            self.idle()
            results["actions_taken"].append("auto_idle")

        if self.state == BrainState.IDLE and (now - self.last_active_time) > self.settings.sleep_timeout:
            self.sleep()
            results["actions_taken"].append("auto_sleep")

        return results

    # ── 消息处理（内部路由） ──

    def _handle_chat(self, message) -> "Response":
        from core.message import Response

        if not self._social:
            return Response.fail("社交模块未初始化")

        result = self.social.send_message(
            from_alpha_id=message.sender,
            to_alpha_id=self.alpha_id,
            content=message.payload.get("text", ""),
        )
        if result.get("success"):
            return Response.ok(data=result, message="消息已送达")
        return Response.fail(result.get("message", "发送消息失败"))

    def _handle_friend_request(self, message) -> "Response":
        from core.message import Response

        if not self._social:
            return Response.fail("社交模块未初始化")

        result = self.social.send_friend_request(
            from_alpha_id=message.sender,
            to_alpha_id=self.alpha_id,
            message=message.payload.get("note", ""),
        )
        if result.get("success"):
            return Response.ok(data=result, message="好友请求已发送")
        return Response.fail(result.get("message", "好友请求失败"))

    def _handle_friend_response(self, message) -> "Response":
        from core.message import Response

        request_id = message.payload.get("request_id", "")
        action = message.payload.get("action", "")
        if action not in ("accept", "reject"):
            return Response.fail("操作必须是 accept 或 reject")

        result = self.social.respond_friend_request(request_id, action)
        if result.get("success"):
            return Response.ok(data=result)
        return Response.fail(result.get("message", "操作失败"))

    def _handle_profile_query(self, message) -> "Response":
        from core.message import Response, Message

        layer = message.payload.get("layer", "public")
        if not self._identity:
            return Response.fail("身份模块未初始化")

        profile = self.identity.get_user_profile(self.alpha_id)
        if not profile:
            return Response.fail("档案不存在")

        # 按可见度过滤
        safe = self._filter_by_visibility(profile, layer, message.sender)
        return Response.ok(data=safe)

    def _handle_app_action(self, message) -> "Response":
        """
        处理外部应用动作（电子宠物、游戏等）。
        外部应用通过标准 Message 格式与 Alpha-ID 交互。
        """
        from core.message import Response

        action = message.payload.get("action", "")
        app_id = message.sender

        # 简单路由：未来可扩展
        if action == "say":
            text = message.payload.get("text", "")
            return Response.ok(data={"echo": text}, message=f"{app_id} 说: {text}")
        elif action == "query_status":
            return Response.ok(data={
                "alpha_id": self.alpha_id,
                "status": self.state.value,
                "is_active": self.is_active(),
            })
        else:
            return Response.fail(f"不支持的外部动作: {action}")

    # ── 可见度过滤 ──

    def _filter_by_visibility(self, profile: Dict, layer: str, requester: str) -> Dict:
        """
        根据查询方与目标的关系，返回对应可见度的数据。
        """
        # 仅自己可见
        if requester == self.alpha_id:
            return dict(profile)

        # 基本信息公开
        safe = {
            "alpha_id": profile.get("alpha_id"),
        }

        if layer == "public":
            safe["nickname"] = profile.get("alpha_id")
            return safe

        # 好友/密友检查（简化版本，未来用社交关系查）
        is_friend = False
        is_close = False
        if self._social:
            friends = self.social.get_friends(self.alpha_id)
            is_friend = any(f.get("alpha_id") == requester for f in friends)
            # 密友检查（未来实现）

        if layer == "friends" and is_friend:
            safe["nickname"] = profile.get("alpha_id")
            safe["bio"] = profile.get("user_id", "")
            safe["devices_count"] = len(profile.get("devices", []))
            return safe

        if layer == "close" and is_close:
            return dict(profile)

        # 权限不足
        return safe

    # ── 工具方法 ──

    def _log_error(self, message: str):
        self.error_log.append({
            "time": datetime.now().isoformat(),
            "message": message,
        })
        # 保留最近 100 条
        if len(self.error_log) > 100:
            self.error_log = self.error_log[-100:]

    def get_status(self) -> Dict[str, Any]:
        """获取大脑完整状态"""
        status = {
            "alpha_id": self.alpha_id,
            "state": self.state.value,
            "is_active": self.is_active(),
            "message_count": self._message_count,
            "last_active": self.last_active_time,
            "active_since": self.active_since,
            "error_count": len(self.error_log),
            "settings": asdict(self.settings),
        }
        if self._actions:
            status["action_engine"] = self.actions.get_stats()
        return status

    def __repr__(self) -> str:
        return f"<TwinBrain {self.alpha_id} [{self.state.value}]>"


# ── 大脑注册表（全局管理所有活跃的大脑） ──

class BrainRegistry:
    """
    孪生大脑注册表 —— 管理系统中所有活跃的 Alpha-ID 大脑实例。

    提供全局的查找、激活、休眠管理。
    """

    def __init__(self):
        self._brains: Dict[str, TwinBrain] = {}

    def register(self, brain: TwinBrain):
        """注册大脑"""
        self._brains[brain.alpha_id] = brain

    def unregister(self, alpha_id: str):
        """注销大脑"""
        self._brains.pop(alpha_id, None)

    def get(self, alpha_id: str) -> Optional[TwinBrain]:
        """获取大脑实例"""
        return self._brains.get(alpha_id)

    def get_or_create(self, alpha_id: str, storage=None) -> TwinBrain:
        """获取已有大脑，或创建新实例"""
        brain = self._brains.get(alpha_id)
        if brain is None:
            brain = TwinBrain(alpha_id=alpha_id, storage=storage)
            self._brains[alpha_id] = brain
        return brain

    def broadcast(self, message) -> List[Dict]:
        """向所有活跃大脑广播消息"""
        from core.message import Response
        results = []
        for brain in self._brains.values():
            if brain.is_active():
                resp = brain.receive(message)
                results.append({"alpha_id": brain.alpha_id, "response": resp.to_dict()})
        return results

    def list_active(self) -> List[TwinBrain]:
        """列出所有活跃的大脑"""
        return [b for b in self._brains.values() if b.is_active()]

    def count(self) -> Dict[str, int]:
        """统计各状态大脑数量"""
        counts = {s.value: 0 for s in BrainState}
        for brain in self._brains.values():
            counts[brain.state.value] += 1
        counts["total"] = len(self._brains)
        return counts

    def __repr__(self) -> str:
        return f"<BrainRegistry: {len(self._brains)} brains>"


# 全局默认注册表
default_registry = BrainRegistry()
