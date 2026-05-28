"""
TwinBrain 核心单元测试 —— 状态机、消息路由、自主学习周期、BrainRegistry
"""
import pytest
import time
from unittest.mock import MagicMock, patch
from core.twin_brain import (
    TwinBrain, BrainRegistry, BrainState, BrainSettings,
    can_transition, BRAIN_TRANSITIONS, default_registry
)
from core.message import Message, Response, MessageType


class TestBrainStateMachine:
    """大脑状态机转换测试"""

    def test_initial_state_is_sleep(self):
        brain = TwinBrain(alpha_id="Alpha-Test-001")
        assert brain.state == BrainState.SLEEP

    def test_can_transition_valid(self):
        """合法的状态转换"""
        assert can_transition(BrainState.SLEEP, BrainState.AWAKE)
        assert can_transition(BrainState.SLEEP, BrainState.IDLE)
        assert can_transition(BrainState.AWAKE, BrainState.IDLE)
        assert can_transition(BrainState.AWAKE, BrainState.SLEEP)
        assert can_transition(BrainState.IDLE, BrainState.AWAKE)
        assert can_transition(BrainState.ERROR, BrainState.SLEEP)

    def test_cannot_transition_invalid(self):
        """非法的状态转换"""
        assert not can_transition(BrainState.SLEEP, BrainState.SLEEP)  # 自身→自身非法
        assert not can_transition(BrainState.AWAKE, BrainState.AWAKE)
        assert not can_transition(BrainState.ERROR, BrainState.ERROR)

    def test_all_transitions_defined(self):
        """所有状态都有出边定义"""
        for state in BrainState:
            assert state in BRAIN_TRANSITIONS, f"{state} 缺少转换规则"

    def test_awake_transition(self):
        brain = TwinBrain(alpha_id="Alpha-Test-002")
        result = brain.awake()
        assert result is True
        assert brain.state == BrainState.AWAKE
        assert brain.active_since > 0

    def test_sleep_transition(self):
        brain = TwinBrain(alpha_id="Alpha-Test-003")
        brain.awake()
        assert brain.state == BrainState.AWAKE
        result = brain.sleep()
        assert result is True
        assert brain.state == BrainState.SLEEP
        assert brain.active_since == 0.0

    def test_idle_transition(self):
        brain = TwinBrain(alpha_id="Alpha-Test-004")
        brain.awake()
        result = brain.idle()
        assert result is True
        assert brain.state == BrainState.IDLE

    def test_illegal_transition_via_can_transition(self):
        """can_transition 对非法转换返回 False"""
        # 自身→自身不在任何转换规则中
        assert not can_transition(BrainState.SLEEP, BrainState.SLEEP)

    def test_same_state_transition_is_noop(self):
        """transition_to 对同状态返回 True（幂等）"""
        brain = TwinBrain(alpha_id="Alpha-Test-005")
        result = brain.transition_to(BrainState.SLEEP)
        assert result is True  # 同状态，幂等返回 True

    def test_is_active(self):
        brain = TwinBrain(alpha_id="Alpha-Test-006")
        assert not brain.is_active()  # SLEEP 不活跃
        brain.awake()
        assert brain.is_active()      # AWAKE 活跃
        brain.idle()
        assert brain.is_active()      # IDLE 活跃
        brain.sleep()
        assert not brain.is_active()  # SLEEP 不活跃


class TestBrainMessageRouting:
    """消息路由测试（无依赖模块的纯路由）"""

    def setup_brain(self, state=BrainState.AWAKE):
        brain = TwinBrain(alpha_id="Alpha-Msg-001")
        brain.awake()
        if state != BrainState.AWAKE:
            brain.transition_to(state)
        return brain

    def test_sleep_refuses_messages(self):
        brain = TwinBrain(alpha_id="Alpha-Msg-002")
        # 默认 SLEEP 状态
        msg = Message.create_chat(sender="Alpha-Other", recipient="Alpha-Msg-002", text="hi")
        resp = brain.receive(msg)
        assert resp.success is False
        assert resp.error_code == "SLEEPING"

    def test_sleep_auto_reply(self):
        brain = TwinBrain(alpha_id="Alpha-Msg-003", settings=BrainSettings(auto_reply=True))
        msg = Message.create_chat(sender="Alpha-Other", recipient="Alpha-Msg-003", text="hi")
        resp = brain.receive(msg)
        assert resp.success is True
        assert resp.data.get("auto_reply") is True

    def test_ping(self):
        brain = self.setup_brain()
        msg = Message(sender="Alpha-Pinger", recipient="Alpha-Msg-001", msg_type=MessageType.PING)
        resp = brain.receive(msg)
        assert resp.success is True
        assert resp.data["alpha_id"] == "Alpha-Msg-001"
        assert resp.data["status"] == "awake"

    def test_app_action_say(self):
        brain = self.setup_brain()
        msg = Message(
            sender="PetApp", recipient="Alpha-Msg-001",
            msg_type=MessageType.APP_ACTION,
            payload={"action": "say", "text": "hello world"}
        )
        resp = brain.receive(msg)
        assert resp.success is True
        assert resp.data["echo"] == "hello world"

    def test_app_action_query_status(self):
        brain = self.setup_brain()
        msg = Message(
            sender="PetApp", recipient="Alpha-Msg-001",
            msg_type=MessageType.APP_ACTION,
            payload={"action": "query_status"}
        )
        resp = brain.receive(msg)
        assert resp.success is True
        assert resp.data["alpha_id"] == "Alpha-Msg-001"
        assert resp.data["is_active"] is True

    def test_app_action_unknown(self):
        brain = self.setup_brain()
        msg = Message(
            sender="PetApp", recipient="Alpha-Msg-001",
            msg_type=MessageType.APP_ACTION,
            payload={"action": "fly"}
        )
        resp = brain.receive(msg)
        assert resp.success is False
        assert "不支持" in resp.message

    def test_unknown_message_type(self):
        brain = self.setup_brain()
        msg = Message(sender="Alpha-X", recipient="Alpha-Msg-001", msg_type="unknown_type")
        resp = brain.receive(msg)
        assert resp.success is False
        assert resp.error_code == "UNSUPPORTED_TYPE"

    def test_error_state_returns_error(self):
        brain = TwinBrain(alpha_id="Alpha-Msg-Error")
        brain.state = BrainState.ERROR
        msg = Message.create_chat(sender="Alpha-X", recipient="Alpha-Msg-Error", text="hi")
        resp = brain.receive(msg)
        assert resp.success is False
        assert resp.error_code == "ERROR"


class TestBrainThinkCycle:
    """自主学习周期测试"""

    def test_think_basic(self):
        """基本 think 返回正确结构"""
        brain = TwinBrain(alpha_id="Alpha-Think-001")
        result = brain.think()
        assert result["alpha_id"] == "Alpha-Think-001"
        assert "state" in result
        assert "message_count" in result
        assert "pending_requests" in result
        assert "actions_taken" in result

    def test_think_increments_not_active(self):
        """think 不会自动切换状态（除非超时）"""
        brain = TwinBrain(alpha_id="Alpha-Think-002")
        assert brain.state == BrainState.SLEEP
        brain.think()
        # 不应自动唤醒
        assert brain.state == BrainState.SLEEP

    def test_think_auto_idle_after_timeout(self):
        """AWAKE 超时后自动转为 IDLE"""
        brain = TwinBrain(alpha_id="Alpha-Think-003")
        brain.settings.idle_timeout = 0  # 立即超时
        brain.awake()
        brain.think()
        assert brain.state == BrainState.IDLE

    def test_think_auto_sleep_after_timeout(self):
        """IDLE 超时后自动转为 SLEEP"""
        brain = TwinBrain(alpha_id="Alpha-Think-004")
        brain.settings.idle_timeout = 0
        brain.settings.sleep_timeout = 0  # 立即超时
        brain.awake()
        brain.think()  # → idle
        brain.think()  # → sleep
        assert brain.state == BrainState.SLEEP

    def test_think_with_action_engine(self):
        """think 触发待执行行动"""
        brain = TwinBrain(alpha_id="Alpha-Think-005")
        brain.awake()
        # 手动触发 action engine 的 lazy 初始化
        engine = brain.actions
        # 规划一个自动批准的行动
        from core.action_engine import Action, ActionType
        action = Action(action_type=ActionType.GET_CONTACTS, platform="console")
        engine.plan(action)
        result = brain.think()
        # 应该有行动被执行
        assert len(result["actions_taken"]) >= 1


class TestBrainActionEngine:
    """通过 TwinBrain 间接测试 ActionEngine 集成"""

    def test_no_action_engine_confirm(self):
        brain = TwinBrain(alpha_id="Alpha-AE-001")
        brain.awake()
        msg = Message(
            sender="User", recipient="Alpha-AE-001",
            msg_type=MessageType.ACTION_CONFIRM,
            payload={"action_id": "nonexistent", "approved": True}
        )
        # _actions 未初始化
        resp = brain.receive(msg)
        assert resp.success is False
        assert resp.error_code == "NO_ACTION_ENGINE"

    def test_action_query_no_engine(self):
        brain = TwinBrain(alpha_id="Alpha-AE-002")
        brain.awake()
        msg = Message(
            sender="User", recipient="Alpha-AE-002",
            msg_type=MessageType.ACTION_QUERY,
            payload={}
        )
        resp = brain.receive(msg)
        assert resp.success is False
        assert resp.error_code == "NO_ACTION_ENGINE"

    def test_action_query_returns_stats(self):
        brain = TwinBrain(alpha_id="Alpha-AE-003")
        brain.awake()
        # 触发行动引擎初始化
        _ = brain.actions
        msg = Message(
            sender="User", recipient="Alpha-AE-003",
            msg_type=MessageType.ACTION_QUERY,
            payload={}
        )
        resp = brain.receive(msg)
        assert resp.success is True
        assert "stats" in resp.data
        assert "pending_approvals" in resp.data


class TestBrainVisibility:
    """可见度过滤测试"""

    def setup_brain_with_profile(self):
        brain = TwinBrain(alpha_id="Alpha-Vis-001")
        profile = {"alpha_id": "Alpha-Vis-001", "nickname": "TestUser", "bio": "Hello", "devices": ["d1"]}
        return brain, profile

    def test_self_sees_all(self):
        brain, profile = self.setup_brain_with_profile()
        result = brain._filter_by_visibility(profile, "public", "Alpha-Vis-001")
        assert result == profile  # 自己看到全部

    def test_public_layer(self):
        brain, profile = self.setup_brain_with_profile()
        result = brain._filter_by_visibility(profile, "public", "Alpha-Stranger")
        assert result == {"alpha_id": "Alpha-Vis-001", "nickname": "Alpha-Vis-001"}

    def test_friends_layer_non_friend(self):
        brain, profile = self.setup_brain_with_profile()
        # social 未初始化 → 无好友
        result = brain._filter_by_visibility(profile, "friends", "Alpha-Stranger")
        assert result == {"alpha_id": "Alpha-Vis-001"}  # 只有 alpha_id

    def test_close_layer_non_close(self):
        brain, profile = self.setup_brain_with_profile()
        result = brain._filter_by_visibility(profile, "close", "Alpha-Stranger")
        assert result == {"alpha_id": "Alpha-Vis-001"}


class TestBrainRegistry:
    """BrainRegistry 测试"""

    def setup(self):
        registry = BrainRegistry()
        brain1 = TwinBrain(alpha_id="Alpha-Reg-001")
        brain2 = TwinBrain(alpha_id="Alpha-Reg-002")
        return registry, brain1, brain2

    def test_register_and_get(self):
        registry, brain1, _ = self.setup()
        registry.register(brain1)
        assert registry.get("Alpha-Reg-001") is brain1

    def test_get_nonexistent(self):
        registry, _, _ = self.setup()
        assert registry.get("Alpha-Reg-None") is None

    def test_unregister(self):
        registry, brain1, _ = self.setup()
        registry.register(brain1)
        registry.unregister("Alpha-Reg-001")
        assert registry.get("Alpha-Reg-001") is None

    def test_get_or_create_new(self):
        registry, _, _ = self.setup()
        brain = registry.get_or_create("Alpha-Reg-New")
        assert brain is not None
        assert brain.alpha_id == "Alpha-Reg-New"
        assert registry.get("Alpha-Reg-New") is brain

    def test_get_or_create_existing(self):
        registry, brain1, _ = self.setup()
        registry.register(brain1)
        brain = registry.get_or_create("Alpha-Reg-001")
        assert brain is brain1  # 同一个对象

    def test_count(self):
        registry, brain1, brain2 = self.setup()
        registry.register(brain1)
        registry.register(brain2)
        stats = registry.count()
        assert stats["total"] == 2
        assert stats["sleep"] == 2  # 默认都是 SLEEP

    def test_list_active(self):
        registry, brain1, brain2 = self.setup()
        brain1.awake()
        registry.register(brain1)
        registry.register(brain2)  # SLEEP
        active = registry.list_active()
        assert len(active) == 1
        assert active[0] is brain1

    def test_broadcast(self):
        registry, brain1, brain2 = self.setup()
        brain1.awake()
        registry.register(brain1)
        registry.register(brain2)
        msg = Message(sender="Tester", recipient="all", msg_type=MessageType.PING)
        results = registry.broadcast(msg)
        # 只有 brain1 活跃
        assert len(results) == 1

    def test_default_registry_is_global(self):
        """默认注册表是单例"""
        from core.twin_brain import default_registry
        assert isinstance(default_registry, BrainRegistry)

    def test_get_status_contains_action_engine_when_initialized(self):
        brain = TwinBrain(alpha_id="Alpha-Status-001")
        status = brain.get_status()
        assert status["alpha_id"] == "Alpha-Status-001"
        assert "action_engine" not in status  # 未初始化
        _ = brain.actions  # 触发行动引擎
        status = brain.get_status()
        assert "action_engine" in status

    def test_repr(self):
        brain = TwinBrain(alpha_id="Alpha-Repr-001")
        assert repr(brain) == "<TwinBrain Alpha-Repr-001 [sleep]>"
        brain.awake()
        assert "awake" in repr(brain)


class TestMessageTypes:
    """Message 和 Response 数据类测试"""

    def test_message_defaults(self):
        msg = Message()
        assert msg.version == "2.0"
        assert msg.message_id != ""
        assert msg.msg_type == "chat"

    def test_message_to_dict(self):
        msg = Message.create_chat(sender="A", recipient="B", text="Hello")
        d = msg.to_dict()
        assert d["sender"] == "A"
        assert d["recipient"] == "B"
        assert d["payload"]["text"] == "Hello"

    def test_message_from_dict(self):
        data = {"sender": "A", "recipient": "B", "msg_type": "chat", "payload": {"text": "Hi"}}
        msg = Message.from_dict(data)
        assert msg.sender == "A"
        assert msg.payload["text"] == "Hi"

    def test_message_from_dict_ignores_extra(self):
        data = {"sender": "A", "recipient": "B", "msg_type": "chat", "extra_field": "ignored"}
        msg = Message.from_dict(data)
        assert not hasattr(msg, "extra_field")

    def test_create_friend_request(self):
        msg = Message.create_friend_request(sender="A", recipient="B", note="Hello friend")
        assert msg.msg_type == "friend_request"
        assert msg.payload["note"] == "Hello friend"

    def test_create_profile_query(self):
        msg = Message.create_profile_query(sender="A", target="B", layer="friends")
        assert msg.msg_type == "profile_query"
        assert msg.payload["layer"] == "friends"

    def test_response_ok(self):
        resp = Response.ok(data={"key": "value"}, message="success")
        assert resp.success is True
        assert resp.data["key"] == "value"

    def test_response_fail(self):
        resp = Response.fail(message="error occurred", error_code="ERR_001")
        assert resp.success is False
        assert resp.error_code == "ERR_001"

    def test_response_to_dict(self):
        resp = Response.ok(data={"a": 1}, message="ok")
        d = resp.to_dict()
        assert d["success"] is True
        assert d["data"]["a"] == 1
