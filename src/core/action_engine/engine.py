"""
行动引擎 —— 行动的执行中枢
"""

from typing import Any, Dict, List, Optional

from .adapters import PlatformAdapter
from .approval import ApprovalGate, ApprovalPolicy
from .models import Action, ActionResult, ActionStatus


class ActionEngine:
    """
    行动引擎：TwinBrain 对外部世界施加影响的执行层。

    职责：
    1. 注册平台适配器
    2. 接收行动请求 → 审批 → 执行 → 记录结果
    3. 管理行动生命周期
    4. 行动失败时提供重试策略
    """

    def __init__(self, alpha_id: str = "", approval_policy: Optional[ApprovalPolicy] = None):
        self._alpha_id = alpha_id
        self._adapters: Dict[str, PlatformAdapter] = {}
        self._approval = ApprovalGate(policy=approval_policy or ApprovalPolicy())
        self._history: List[Action] = []  # 全部行动历史
        self._pending: Dict[str, Action] = {}  # 待执行（已批准）
        self._max_history = 1000

    # ── 适配器管理 ──

    def register_adapter(self, adapter: PlatformAdapter) -> None:
        """注册一个平台适配器"""
        self._adapters[adapter.platform_name] = adapter
        print(f"[ActionEngine] 注册平台适配器: {adapter.platform_name}")

    def get_adapter(self, platform: str) -> Optional[PlatformAdapter]:
        return self._adapters.get(platform)

    def list_adapters(self) -> Dict[str, Any]:
        return {name: adapter.get_capabilities() for name, adapter in self._adapters.items()}

    # ── 核心流程 ──

    def plan(self, action: Action) -> Action:
        """
        第一步：计划一个行动

        做审批评估，如果自动通过则进入待执行队列。
        如果需要用户确认，停留在 PENDING 状态等待外部调用 confirm()。

        Returns:
            更新了 status 和 approval_level 的 Action 对象
        """
        # 验证平台是否存在
        if action.platform and action.platform not in self._adapters:
            action.status = ActionStatus.FAILED
            action.result = ActionResult(
                success=False,
                message=f"未注册的平台: {action.platform}，可用平台: {list(self._adapters.keys())}",
                error_code="PLATFORM_NOT_FOUND",
            )
            self._add_history(action)
            return action

        # 验证适配器
        adapter = self._adapters.get(action.platform) if action.platform else None
        if adapter:
            validation_error = adapter.validate(action)
            if validation_error:
                action.status = ActionStatus.FAILED
                action.result = ActionResult(
                    success=False,
                    message=validation_error,
                    error_code="VALIDATION_ERROR",
                )
                self._add_history(action)
                return action

        # 审批
        action = self._approval.check(action)

        # 自动通过的 → 进入待执行
        if action.status == ActionStatus.APPROVED:
            self._pending[action.action_id] = action

        self._add_history(action)
        return action

    def execute(self, action_id: str) -> Optional[Action]:
        """
        第二步：执行一个已批准的行动

        Args:
            action_id: 行动 ID
        """
        action = self._pending.pop(action_id, None)
        if not action:
            return None

        if action.status != ActionStatus.APPROVED:
            action.status = ActionStatus.FAILED
            action.result = ActionResult(
                success=False,
                message=f"行动状态不允许执行: {action.status.name}",
                error_code="INVALID_STATE",
            )
            self._add_history(action)
            return action

        # 查找适配器
        adapter = self._adapters.get(action.platform)
        if not adapter:
            action.status = ActionStatus.FAILED
            action.result = ActionResult(
                success=False,
                message=f"未找到平台适配器: {action.platform}",
                error_code="ADAPTER_NOT_FOUND",
            )
            self._add_history(action)
            return action

        # 执行
        action.mark_running()
        try:
            result = adapter.execute(action)
            action.mark_done(result)
        except Exception as e:
            action.status = ActionStatus.FAILED
            action.result = ActionResult(
                success=False,
                message=f"执行异常: {str(e)}",
                error_code="EXECUTION_ERROR",
            )

        self._add_history(action)
        return action

    def plan_and_execute(self, action: Action) -> Action:
        """
        快捷方式：计划 + 自动执行一步完成

        只对 AUTO / NOTIFY 级别的行动有效。
        CONFIRM / REVIEW 级别的行动需要先 plan，再通过 confirm 批准后手动 execute。
        """
        action = self.plan(action)
        if action.status == ActionStatus.APPROVED and action.action_id in self._pending:
            action = self.execute(action.action_id)
        return action

    # ── 审批交互 ──

    def confirm(self, action_id: str, approved: bool, note: str = "") -> Optional[Action]:
        """
        用户回应审批请求

        Args:
            action_id: 行动 ID
            approved: 是否批准
            note: 用户备注
        """
        action = self._approval.confirm(action_id, approved, note)
        if action and approved:
            self._pending[action.action_id] = action
        return action

    def list_pending_approvals(self) -> List[Dict[str, Any]]:
        """列出待审批的行动（给用户看）"""
        return [a.to_dict() for a in self._approval.list_pending()]

    # ── 历史查询 ──

    def get_history(self, limit: int = 20, status_filter: Optional[ActionStatus] = None) -> List[Dict[str, Any]]:
        """查询行动历史"""
        results = self._history[-limit:] if limit else self._history[:]
        if status_filter:
            results = [a for a in results if a.status == status_filter]
        return [a.to_dict() for a in results]

    def get_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        """查询单个行动详情"""
        for a in self._history:
            if a.action_id == action_id:
                return a.to_dict()
        # 也查待执行队列
        if action_id in self._pending:
            return self._pending[action_id].to_dict()
        return None

    def get_stats(self) -> Dict[str, int]:
        """行动统计"""
        total = len(self._history)
        by_status = {}
        for a in self._history:
            s = a.status.name
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total_actions": total,
            "pending_approvals": len(self._approval.list_pending()),
            "pending_execution": len(self._pending),
            **by_status,
        }

    # ── 内部 ──

    def _add_history(self, action: Action) -> None:
        self._history.append(action)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

    def get_pending_actions(self) -> List[Action]:
        """获取待执行行动列表（内部用）"""
        return list(self._pending.values())
