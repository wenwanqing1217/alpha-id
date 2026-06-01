"""
ActionEngine 单元测试 —— 行动引擎、审批流、平台适配器
"""

import pytest
from core.action_engine import (
    ActionEngine,
    Action,
    ActionResult,
    ActionType,
    ActionStatus,
    ApprovalLevel,
    ApprovalGate,
    ApprovalPolicy,
    ConsoleAdapter,
)


class TestActionModel:
    """Action 数据模型测试"""

    def test_action_defaults(self):
        action = Action()
        assert action.action_id != ""
        assert action.status == ActionStatus.PENDING
        assert action.approval_level == ApprovalLevel.AUTO

    def test_action_approve(self):
        action = Action()
        action.approve()
        assert action.status == ActionStatus.APPROVED

    def test_action_reject(self):
        action = Action()
        action.reject("不合法")
        assert action.status == ActionStatus.REJECTED
        assert action.metadata["reject_reason"] == "不合法"

    def test_action_cancel(self):
        action = Action()
        action.cancel()
        assert action.status == ActionStatus.CANCELLED

    def test_mark_running(self):
        action = Action()
        action.mark_running()
        assert action.status == ActionStatus.RUNNING

    def test_mark_done_success(self):
        action = Action()
        result = ActionResult(success=True, message="OK")
        action.mark_done(result)
        assert action.status == ActionStatus.SUCCESS
        assert action.result.message == "OK"

    def test_mark_done_failure(self):
        action = Action()
        result = ActionResult(success=False, message="Failed")
        action.mark_done(result)
        assert action.status == ActionStatus.FAILED
        assert action.result.message == "Failed"

    def test_to_dict(self):
        action = Action(action_type=ActionType.POST, platform="console", intent="测试发布")
        d = action.to_dict()
        assert d["action_type"] == "POST"
        assert d["status"] == "PENDING"
        assert d["approval_level"] == "AUTO"
        assert d["intent"] == "测试发布"

    def test_to_dict_with_result(self):
        action = Action()
        result = ActionResult(success=True, message="OK", data={"id": 123})
        action.mark_done(result)
        d = action.to_dict()
        assert d["result"]["success"] is True
        assert d["result"]["data"]["id"] == 123

    def test_create_post_factory(self):
        action = Action.create_post(platform="wechat", content="Hello world!", source_alpha_id="Alpha-001")
        assert action.action_type == ActionType.POST
        assert action.platform == "wechat"
        assert action.payload["content"] == "Hello world!"
        assert action.source_alpha_id == "Alpha-001"
        assert "post" in action.tags

    def test_create_message_factory(self):
        action = Action.create_message(
            platform="wechat", recipient="Alpha-002", content="Hi there", source_alpha_id="Alpha-001"
        )
        assert action.action_type == ActionType.SEND_MESSAGE
        assert action.payload["recipient"] == "Alpha-002"
        assert action.payload["content"] == "Hi there"


class TestApprovalPolicy:
    """审批策略测试"""

    def setup(self):
        return ApprovalPolicy()

    def test_auto_actions(self):
        policy = self.setup()
        action = Action(action_type=ActionType.GET_CONTACTS)
        level = policy.evaluate(action)
        assert level == ApprovalLevel.AUTO

    def test_notify_actions(self):
        policy = self.setup()
        action = Action(action_type=ActionType.SEND_MESSAGE)
        level = policy.evaluate(action)
        assert level == ApprovalLevel.NOTIFY

    def test_confirm_actions(self):
        policy = self.setup()
        action = Action(action_type=ActionType.SEND_LINK)
        level = policy.evaluate(action)
        assert level == ApprovalLevel.CONFIRM

    def test_review_actions(self):
        policy = self.setup()
        action = Action(action_type=ActionType.POST)
        level = policy.evaluate(action)
        assert level == ApprovalLevel.REVIEW

    def test_platform_override(self):
        """平台+类型覆盖规则"""
        policy = self.setup()
        # wechat_POST → REVIEW（默认 POST 就是 REVIEW）
        action = Action(action_type=ActionType.POST, platform="wechat")
        level = policy.evaluate(action)
        assert level == ApprovalLevel.REVIEW
        # feishu_POST → NOTIFY（覆盖为 NOTIFY）
        action2 = Action(action_type=ActionType.POST, platform="feishu")
        level2 = policy.evaluate(action2)
        assert level2 == ApprovalLevel.NOTIFY

    def test_high_risk_escalation(self):
        """高风险时自动升级"""
        policy = self.setup()
        # GET_CONTACTS 默认 AUTO
        action = Action(action_type=ActionType.GET_CONTACTS)
        # 高风险（>50）
        level = policy.evaluate(action, risk_score=80)
        assert level == ApprovalLevel.NOTIFY  # 从 AUTO 升级到 NOTIFY

    def test_high_risk_no_escalation_for_confirm(self):
        """高风险但不降低已有级别"""
        policy = self.setup()
        action = Action(action_type=ActionType.SEND_LINK)  # 默认 CONFIRM
        level = policy.evaluate(action, risk_score=80)
        assert level == ApprovalLevel.CONFIRM  # CONFIRM 不会降到更低

    def test_add_override(self):
        policy = self.setup()
        policy.add_override("console_EXECUTE", ApprovalLevel.BLOCK)
        action = Action(action_type=ActionType.EXECUTE, platform="console")
        level = policy.evaluate(action)
        assert level == ApprovalLevel.BLOCK

    def test_unknown_type_defaults_to_confirm(self):
        policy = self.setup()
        # 模拟未知 ActionType
        from unittest.mock import MagicMock

        action = MagicMock(spec=Action)
        action.action_type.name = "UNKNOWN_TYPE"
        action.platform = ""
        level = policy.evaluate(action)
        assert level == ApprovalLevel.CONFIRM


class TestApprovalGate:
    """审批门测试"""

    def setup(self):
        policy = ApprovalPolicy()
        return ApprovalGate(policy=policy)

    def test_auto_approves(self):
        gate = self.setup()
        action = Action(action_type=ActionType.GET_CONTACTS)
        result = gate.check(action)
        assert result.status == ActionStatus.APPROVED
        assert result.approval_level == ApprovalLevel.AUTO

    def test_notify_approves(self):
        gate = self.setup()
        action = Action(action_type=ActionType.SEND_MESSAGE)
        result = gate.check(action)
        assert result.status == ActionStatus.APPROVED
        assert result.approval_level == ApprovalLevel.NOTIFY

    def test_confirm_pending(self):
        gate = self.setup()
        action = Action(action_type=ActionType.SEND_LINK)
        result = gate.check(action)
        assert result.status == ActionStatus.PENDING  # 等待确认
        assert result.action_id in [a.action_id for a in gate.list_pending()]

    def test_review_pending(self):
        gate = self.setup()
        action = Action(action_type=ActionType.POST)
        result = gate.check(action)
        assert result.status == ActionStatus.PENDING

    def test_block_rejects(self):
        policy = ApprovalPolicy()
        policy.add_override("console_EXECUTE", ApprovalLevel.BLOCK)
        gate = ApprovalGate(policy=policy)
        action = Action(action_type=ActionType.EXECUTE, platform="console")
        result = gate.check(action)
        assert result.status == ActionStatus.REJECTED

    def test_confirm_approved(self):
        gate = self.setup()
        action = Action(action_type=ActionType.SEND_LINK)
        gate.check(action)
        result = gate.confirm(action.action_id, approved=True)
        assert result is not None
        assert result.status == ActionStatus.APPROVED
        # 确认后应从待审批列表中移除
        assert gate.get_pending(action.action_id) is None

    def test_confirm_rejected(self):
        gate = self.setup()
        action = Action(action_type=ActionType.SEND_LINK)
        gate.check(action)
        result = gate.confirm(action.action_id, approved=False, note="暂不需要")
        assert result is not None
        assert result.status == ActionStatus.REJECTED
        assert result.metadata.get("reject_reason") == "暂不需要"

    def test_confirm_nonexistent(self):
        gate = self.setup()
        result = gate.confirm("nonexistent_id", approved=True)
        assert result is None

    def test_list_pending_filter(self):
        gate = self.setup()
        a1 = Action(action_type=ActionType.SEND_LINK, source_alpha_id="Alpha-A")
        a2 = Action(action_type=ActionType.POST, source_alpha_id="Alpha-B")
        gate.check(a1)
        gate.check(a2)
        pending_a = gate.list_pending(alpha_id="Alpha-A")
        assert len(pending_a) == 1
        assert pending_a[0].source_alpha_id == "Alpha-A"
        pending_all = gate.list_pending()
        assert len(pending_all) == 2


class TestActionEngine:
    """ActionEngine 核心流程测试"""

    def setup(self):
        engine = ActionEngine(alpha_id="Alpha-Engine-001")
        engine.register_adapter(ConsoleAdapter())
        return engine

    def test_initial_state(self):
        engine = self.setup()
        assert engine._alpha_id == "Alpha-Engine-001"
        assert len(engine._adapters) == 1
        assert engine._history == []
        assert engine._pending == {}

    def test_plan_auto_action(self):
        """AUTO 级别的行动 plan 后进入待执行队列"""
        engine = self.setup()
        action = Action(action_type=ActionType.GET_CONTACTS, platform="console")
        result = engine.plan(action)
        assert result.status == ActionStatus.APPROVED
        assert result.action_id in engine._pending
        assert len(engine._history) == 1

    def test_plan_notify_action(self):
        """NOTIFY 级别的行动 plan 后进入待执行队列"""
        engine = self.setup()
        action = Action(action_type=ActionType.SEND_MESSAGE, platform="console")
        result = engine.plan(action)
        assert result.status == ActionStatus.APPROVED

    def test_plan_confirm_action_not_pending_execution(self):
        """CONFIRM 级别的行动 plan 后不进入待执行队列"""
        engine = self.setup()
        action = Action(action_type=ActionType.SEND_LINK, platform="console")
        result = engine.plan(action)
        assert result.status == ActionStatus.PENDING  # 待审批
        assert result.action_id not in engine._pending  # 不在待执行队列

    def test_plan_unknown_platform_fails(self):
        engine = self.setup()
        action = Action(action_type=ActionType.POST, platform="nonexistent")
        result = engine.plan(action)
        assert result.status == ActionStatus.FAILED
        assert result.result.error_code == "PLATFORM_NOT_FOUND"

    def test_execute_approved_action(self):
        engine = self.setup()
        action = Action(action_type=ActionType.GET_CONTACTS, platform="console")
        engine.plan(action)
        result = engine.execute(action.action_id)
        assert result is not None
        assert result.status == ActionStatus.SUCCESS
        assert result.result.success is True

    def test_execute_nonexistent(self):
        engine = self.setup()
        result = engine.execute("nonexistent_id")
        assert result is None

    def test_execute_not_approved(self):
        """尝试执行未批准的 action"""
        engine = self.setup()
        action = Action(action_type=ActionType.SEND_LINK, platform="console")
        engine.plan(action)  # PENDING
        # 尝试直接执行（但不在待执行队列中）
        result = engine.execute(action.action_id)
        assert result is None

    def test_execute_no_adapter(self):
        engine = ActionEngine(alpha_id="Alpha-Engine-002")
        # 没有注册任何适配器
        action = Action(action_type=ActionType.GET_CONTACTS, platform="console")
        action.approve()
        engine._pending[action.action_id] = action
        result = engine.execute(action.action_id)
        assert result is not None
        assert result.status == ActionStatus.FAILED
        assert result.result.error_code == "ADAPTER_NOT_FOUND"

    def test_plan_and_execute_auto(self):
        """快捷方法：自动计划+执行"""
        engine = self.setup()
        action = Action(action_type=ActionType.GET_CONTACTS, platform="console")
        result = engine.plan_and_execute(action)
        assert result.status == ActionStatus.SUCCESS

    def test_plan_and_execute_confirm(self):
        """快捷方法：CONFIRM 级别无法自动执行"""
        engine = self.setup()
        action = Action(action_type=ActionType.SEND_LINK, platform="console")
        result = engine.plan_and_execute(action)
        assert result.status == ActionStatus.PENDING  # 停留在待审批

    def test_confirm_and_execute(self):
        """完整流程：plan → confirm → execute"""
        engine = self.setup()
        action = Action(action_type=ActionType.SEND_LINK, platform="console")
        engine.plan(action)
        engine.confirm(action.action_id, approved=True)
        result = engine.execute(action.action_id)
        assert result is not None
        assert result.status == ActionStatus.SUCCESS

    def test_get_history(self):
        engine = self.setup()
        for i in range(3):
            a = Action(action_type=ActionType.GET_CONTACTS, platform="console", intent=f"Action-{i}")
            engine.plan(a)
        history = engine.get_history(limit=2)
        assert len(history) == 2
        assert "intent" in history[0]

    def test_get_history_with_filter(self):
        engine = self.setup()
        engine.plan(Action(action_type=ActionType.GET_CONTACTS, platform="console"))
        engine.plan(Action(action_type=ActionType.SEND_LINK, platform="console"))
        approved = engine.get_history(limit=20, status_filter=ActionStatus.APPROVED)
        pending = engine.get_history(limit=20, status_filter=ActionStatus.PENDING)
        assert len(approved) >= 1
        assert len(pending) >= 1

    def test_get_history_max(self):
        engine = self.setup()
        engine._max_history = 5
        for i in range(10):
            a = Action(action_type=ActionType.GET_CONTACTS, platform="console")
            engine.plan(a)
        assert len(engine._history) == 5

    def test_get_action_by_id(self):
        engine = self.setup()
        action = Action(action_type=ActionType.GET_CONTACTS, platform="console")
        engine.plan(action)
        result = engine.get_action(action.action_id)
        assert result is not None
        assert result["action_id"] == action.action_id

    def test_get_stats(self):
        engine = self.setup()
        engine.plan(Action(action_type=ActionType.GET_CONTACTS, platform="console"))
        engine.plan(Action(action_type=ActionType.SEND_LINK, platform="console"))
        stats = engine.get_stats()
        assert stats["total_actions"] == 2
        assert stats["pending_approvals"] >= 1  # SEND_LINK 在等审批
        assert stats["pending_execution"] >= 0

    def test_list_pending_approvals(self):
        engine = self.setup()
        engine.plan(Action(action_type=ActionType.POST, platform="console"))
        pending = engine.list_pending_approvals()
        assert len(pending) >= 1
        assert pending[0]["status"] == "PENDING"

    def test_get_pending_actions(self):
        engine = self.setup()
        engine.plan(Action(action_type=ActionType.GET_CONTACTS, platform="console"))
        pending = engine.get_pending_actions()
        assert len(pending) == 1

    def test_adapter_management(self):
        engine = self.setup()
        adapters = engine.list_adapters()
        assert "console" in adapters
        assert adapters["console"]["platform"] == "console"
        assert engine.get_adapter("console") is not None
        assert engine.get_adapter("nonexistent") is None


class TestConsoleAdapter:
    """ConsoleAdapter 具体执行测试"""

    def test_platform_name(self):
        adapter = ConsoleAdapter()
        assert adapter.platform_name == "console"

    def test_execute_post(self):
        adapter = ConsoleAdapter()
        action = Action.create_post(platform="console", content="Test post")
        result = adapter.execute(action)
        assert result.success is True
        assert "已模拟执行" in result.message
        assert result.data["simulated"] is True

    def test_execute_message(self):
        adapter = ConsoleAdapter()
        action = Action.create_message(platform="console", recipient="Alpha-X", content="Hello")
        result = adapter.execute(action)
        assert result.success is True

    def test_get_capabilities(self):
        adapter = ConsoleAdapter()
        caps = adapter.get_capabilities()
        assert caps["platform"] == "console"
        assert "POST" in caps["actions"]
        assert caps["authenticated"] is True

    def test_validate_passes(self):
        adapter = ConsoleAdapter()
        action = Action(action_type=ActionType.POST, platform="console")
        assert adapter.validate(action) is None


class TestActionResult:
    """ActionResult 数据类测试"""

    def test_defaults(self):
        result = ActionResult(success=True)
        assert result.message == ""
        assert result.data == {}
        assert result.error_code is None

    def test_to_dict(self):
        result = ActionResult(success=True, message="OK", data={"id": 1})
        d = result.to_dict()
        assert d["success"] is True
        assert d["message"] == "OK"
        assert d["data"]["id"] == 1
        assert "executed_at" in d
