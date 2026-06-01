"""
审批流 —— 决定一个行动是自动执行还是需要用户确认
"""

from typing import Dict, Optional

from .models import Action, ActionType, ApprovalLevel


class ApprovalPolicy:
    """
    审批策略：根据行动属性决定审批级别

    可扩展：未来可以基于记忆分析用户的偏好，
    或根据风险引擎的评分动态调整级别。
    """

    def __init__(self, risk_threshold: int = 50):
        # 默认审批级别映射（行动类型 → 审批级别）
        self._type_defaults: Dict[str, ApprovalLevel] = {
            ActionType.POST.name: ApprovalLevel.REVIEW,  # 发布内容 → 需要审查
            ActionType.REPLY.name: ApprovalLevel.NOTIFY,  # 回复 → 自动但通知
            ActionType.SEND_MESSAGE.name: ApprovalLevel.NOTIFY,  # 发消息 → 自动但通知
            ActionType.SEND_IMAGE.name: ApprovalLevel.NOTIFY,  # 发图片 → 自动但通知
            ActionType.SEND_FILE.name: ApprovalLevel.NOTIFY,  # 发文件 → 自动但通知
            ActionType.SEND_LINK.name: ApprovalLevel.CONFIRM,  # 发链接 → 需要确认（外部链接有风险）
            ActionType.ADD_FRIEND.name: ApprovalLevel.CONFIRM,  # 加好友 → 需要确认
            ActionType.CREATE_GROUP.name: ApprovalLevel.REVIEW,  # 建群 → 需要审查
            ActionType.GET_CONTACTS.name: ApprovalLevel.AUTO,  # 获取联系人 → 自动
            ActionType.CREATE_DOC.name: ApprovalLevel.AUTO,  # 创建文档 → 自动
            ActionType.SCHEDULE.name: ApprovalLevel.AUTO,  # 设日程 → 自动
            ActionType.EXECUTE.name: ApprovalLevel.CONFIRM,  # 执行命令 → 需要确认
            ActionType.CUSTOM.name: ApprovalLevel.CONFIRM,  # 自定义 → 需要确认
        }
        self._risk_threshold = risk_threshold

        # 覆盖规则：平台 + 行动类型 → 审批级别
        self._overrides: Dict[str, ApprovalLevel] = {
            # 社交平台发帖默认都要审查
            "wechat_POST": ApprovalLevel.REVIEW,
            "xiaohongshu_POST": ApprovalLevel.REVIEW,
            "feishu_POST": ApprovalLevel.NOTIFY,
        }

    def evaluate(self, action: Action, risk_score: Optional[int] = None) -> ApprovalLevel:
        """
        评估一个行动需要的审批级别
        """
        # 1. 检查是否有平台+类型的覆盖规则
        override_key = f"{action.platform}_{action.action_type.name}"
        if override_key in self._overrides:
            return self._overrides[override_key]

        # 2. 用风险评分加严
        if risk_score is not None and risk_score > self._risk_threshold:
            # 高风险 → 至少需要确认
            base = self._type_defaults.get(action.action_type.name, ApprovalLevel.CONFIRM)
            if base == ApprovalLevel.AUTO:
                return ApprovalLevel.NOTIFY
            return base

        # 3. 返回类型默认级别
        return self._type_defaults.get(action.action_type.name, ApprovalLevel.CONFIRM)

    def add_override(self, key: str, level: ApprovalLevel) -> None:
        """添加覆盖规则"""
        self._overrides[key] = level


class ApprovalGate:
    """
    审批门：用户确认行动的执行入口

    支持同步（立刻确认）和异步（等待用户确认）。
    与 TwinBrain 的 receive 机制打通——用户通过 Message 回应审批。
    """

    def __init__(self, policy: Optional[ApprovalPolicy] = None):
        self.policy = policy or ApprovalPolicy()
        self._pending: Dict[str, Action] = {}  # action_id → Action

    def check(self, action: Action, risk_score: Optional[int] = None) -> Action:
        """
        检查行动是否需要审批并更新其状态

        返回更新后的 Action 对象
        """
        level = self.policy.evaluate(action, risk_score)
        action.approval_level = level

        if level == ApprovalLevel.AUTO:
            action.approve()
        elif level == ApprovalLevel.NOTIFY:
            action.approve()
            # 通知标记已记录在 approval_level 上
        elif level in (ApprovalLevel.CONFIRM, ApprovalLevel.REVIEW):
            self._pending[action.action_id] = action
            # 状态保持 PENDING，等待用户确认
        elif level == ApprovalLevel.BLOCK:
            action.reject("该操作被安全策略阻止")

        return action

    def confirm(self, action_id: str, approved: bool, note: str = "") -> Optional[Action]:
        """
        用户对审批的回应

        Args:
            action_id: 行动 ID
            approved: 是否批准
            note: 用户备注（如修改内容）
        """
        action = self._pending.pop(action_id, None)
        if not action:
            return None

        if approved:
            action.approve()
            if note:
                action.metadata["approval_note"] = note
        else:
            action.reject(note)

        return action

    def list_pending(self, alpha_id: str = "") -> list:
        """列出待审批的行动"""
        if alpha_id:
            return [a for a in self._pending.values() if a.source_alpha_id == alpha_id]
        return list(self._pending.values())

    def get_pending(self, action_id: str) -> Optional[Action]:
        return self._pending.get(action_id)
