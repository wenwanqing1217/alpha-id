"""
Alpha-ID 记忆分区工具

核心功能：
1. 定义记忆敏感度等级（公共/私人/核心隐私）
2. 根据风险评分和敏感度判断访问权限
3. 支持摘要式回答
4. 支持声纹验证

作者：Agent搭建专家
日期：2025-06-18
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from langchain.tools import tool, ToolRuntime


class MemoryType(Enum):
    """记忆类型枚举"""
    PUBLIC = "public"           # 公共记忆层（敏感度 0-20）
    PRIVATE = "private"         # 私人记忆层（敏感度 20-60）
    CORE_PRIVACY = "core_privacy"  # 核心隐私层（敏感度 60-100)


class AccessLevel(Enum):
    """访问级别枚举"""
    FULL = "full"               # 完全访问
    SUMMARY = "summary"         # 摘要式访问
    DENIED = "denied"           # 拒绝访问


@dataclass
class MemoryAccessResult:
    """记忆访问结果"""
    access_level: str           # "full", "summary", "denied"
    reason: str                 # 访问决定的原因
    requires_voice: bool        # 是否需要声纹验证
    data: Optional[Dict]        # 实际返回的数据
    warning: Optional[str]      # 警告信息


class MemoryPartitionSystem:
    """记忆分区系统"""

    def __init__(self):
        # 记忆类型与敏感度映射
        self.sensitivity_map = {
            # 公共记忆层（敏感度 0-20）
            "preferences": 10,          # 通用偏好（如喜欢咖啡）
            "location_public": 15,      # 常去地点（如北京、上海）
            "interests": 10,            # 兴趣爱好
            "work_field": 18,           # 工作领域
            "education_public": 12,     # 公开教育背景

            # 私人记忆层（敏感度 20-60）
            "spending_habits": 40,      # 消费习惯
            "monthly_expense": 45,      # 月消费水平
            "personal_goals": 50,       # 个人目标
            "health_info": 55,          # 健康信息
            "schedule": 35,             # 日程安排
            "contact_partial": 30,      # 部分联系人

            # 核心隐私层（敏感度 60-100）
            "id_card": 95,              # 身份证信息
            "bank_account": 95,         # 银行账户
            "passwords": 98,            # 密码
            "phone_number": 85,         # 电话号码
            "home_address": 80,         # 家庭住址
            "emotional_records": 75,    # 深度情感记录
            "contact_full": 70,         # 完整通讯录
            "financial_records": 90,    # 财务记录
            "medical_records": 85       # 医疗记录
        }

        # 初始风险阈值
        self.safe_threshold = 20.0
        self.caution_threshold = 60.0

    def get_sensitivity(self, memory_type: str) -> int:
        """获取记忆类型的敏感度"""
        return self.sensitivity_map.get(memory_type, 50)  # 默认中等敏感度

    def get_memory_category(self, sensitivity: int) -> str:
        """根据敏感度获取记忆分类"""
        if sensitivity < 20:
            return "public"
        elif sensitivity < 60:
            return "private"
        else:
            return "core_privacy"

    def check_access(
        self,
        memory_type: str,
        risk_score: float,
        voice_verified: bool = False
    ) -> MemoryAccessResult:
        """
        检查是否有权访问某类记忆

        Args:
            memory_type: 记忆类型（如 "spending_habits", "id_card"）
            risk_score: 风险评分（0-100）
            voice_verified: 是否已通过声纹验证

        Returns:
            MemoryAccessResult: 访问结果
        """
        sensitivity = self.get_sensitivity(memory_type)
        category = self.get_memory_category(sensitivity)

        # 公共记忆层：直接访问
        if category == "public":
            return MemoryAccessResult(
                access_level="full",
                reason="public_memory_no_verification_needed",
                requires_voice=False,
                data=None,
                warning=None
            )

        # 私人记忆层：根据风险评分决定
        elif category == "private":
            if risk_score < self.safe_threshold:
                # 安全区：完全访问
                return MemoryAccessResult(
                    access_level="full",
                    reason="safe_zone_full_access",
                    requires_voice=False,
                    data=None,
                    warning=None
                )
            elif risk_score < self.caution_threshold:
                # 警戒区：摘要式访问
                return MemoryAccessResult(
                    access_level="summary",
                    reason="caution_zone_summary_access",
                    requires_voice=False,
                    data=None,
                    warning="当前处于警戒区，仅返回摘要信息"
                )
            else:
                # 危险区：拒绝访问，需要声纹验证
                return MemoryAccessResult(
                    access_level="denied",
                    reason="danger_zone_access_denied",
                    requires_voice=True,
                    data=None,
                    warning="风险过高，需要声纹验证后才能访问"
                )

        # 核心隐私层：必须声纹验证
        else:  # core_privacy
            if voice_verified:
                return MemoryAccessResult(
                    access_level="full",
                    reason="voice_verified_full_access",
                    requires_voice=False,
                    data=None,
                    warning="已通过声纹验证，完全访问核心隐私"
                )
            else:
                return MemoryAccessResult(
                    access_level="denied",
                    reason="core_privacy_requires_voice_verification",
                    requires_voice=True,
                    data=None,
                    warning="核心隐私层必须通过声纹验证"
                )

    def generate_summary(self, memory_type: str, full_data: Dict) -> Dict:
        """
        生成摘要式回答

        将详细数据转换为摘要信息，隐藏敏感细节
        """
        summary = {}

        if memory_type == "spending_habits":
            # 消费习惯：只给趋势，不给具体金额
            summary = {
                "trend": full_data.get("trend", "stable"),
                "category_distribution": full_data.get("category_distribution", {}),
                "insights": [
                    "本月消费趋势平稳",
                    "餐饮支出占比相对较高"
                ]
            }
        elif memory_type == "monthly_expense":
            # 月消费：只给范围
            amount = full_data.get("amount", 0)
            summary = {
                "range": f"{int(amount // 1000) * 1000}-{int((amount // 1000 + 1) * 1000)}",
                "trend": full_data.get("trend", "stable")
            }
        elif memory_type == "personal_goals":
            # 个人目标：只给进度百分比
            summary = {
                "goals": [
                    {"name": goal["name"], "progress": f"{goal['progress']}%"}
                    for goal in full_data.get("goals", [])
                ]
            }
        else:
            # 默认摘要：只返回字段名，不返回值
            summary = {
                "available_fields": list(full_data.keys()),
                "note": "详细数据需要更高权限"
            }

        return summary


# 全局系统实例
_system = MemoryPartitionSystem()


@tool
def access_memory(
    memory_type: str,
    full_data: Dict,
    risk_score: float,
    voice_verified: bool = False,
    runtime: ToolRuntime = None
) -> str:
    """
    访问记忆数据（带权限检查）

    Args:
        memory_type: 记忆类型（如 "spending_habits", "id_card", "preferences"）
        full_data: 完整的记忆数据（JSON对象）
        risk_score: 当前风险评分（0-100）
        voice_verified: 是否已通过声纹验证（默认False）

    Returns:
        JSON格式的访问结果，包含：
        - access_level: 访问级别（full/summary/denied）
        - reason: 访问决定的原因
        - requires_voice: 是否需要声纹验证
        - data: 实际返回的数据（根据访问级别可能是完整数据、摘要或None）
        - warning: 警告信息
    """
    ctx = runtime.context if runtime else None

    try:
        # 检查访问权限
        result = _system.check_access(memory_type, risk_score, voice_verified)

        # 根据访问级别返回数据
        if result.access_level == "full":
            result.data = full_data
        elif result.access_level == "summary":
            result.data = _system.generate_summary(memory_type, full_data)
        else:  # denied
            result.data = None

        return json.dumps(asdict(result), ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"记忆访问失败: {str(e)}",
            "access_level": "denied",
            "reason": "system_error",
            "requires_voice": True,
            "data": None,
            "warning": "系统异常，请稍后重试"
        }, ensure_ascii=False, indent=2)


@tool
def list_memory_categories(runtime: ToolRuntime = None) -> str:
    """
    列出所有记忆类型及其敏感度

    Returns:
        JSON格式的记忆类型列表，包含：
        - memory_type: 记忆类型
        - sensitivity: 敏感度（0-100）
        - category: 分类（public/private/core_privacy）
        - description: 描述
    """
    ctx = runtime.context if runtime else None

    try:
        result = []

        descriptions = {
            "preferences": "通用偏好（如喜欢咖啡）",
            "location_public": "常去地点（如北京、上海）",
            "interests": "兴趣爱好",
            "work_field": "工作领域",
            "education_public": "公开教育背景",
            "spending_habits": "消费习惯",
            "monthly_expense": "月消费水平",
            "personal_goals": "个人目标",
            "health_info": "健康信息",
            "schedule": "日程安排",
            "contact_partial": "部分联系人",
            "id_card": "身份证信息",
            "bank_account": "银行账户",
            "passwords": "密码",
            "phone_number": "电话号码",
            "home_address": "家庭住址",
            "emotional_records": "深度情感记录",
            "contact_full": "完整通讯录",
            "financial_records": "财务记录",
            "medical_records": "医疗记录"
        }

        for memory_type, sensitivity in _system.sensitivity_map.items():
            category = _system.get_memory_category(sensitivity)

            result.append({
                "memory_type": memory_type,
                "sensitivity": sensitivity,
                "category": category,
                "description": descriptions.get(memory_type, "")
            })

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"获取记忆类型列表失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
def update_memory_sensitivity(
    memory_type: str,
    new_sensitivity: int,
    runtime: ToolRuntime = None
) -> str:
    """
    更新记忆类型的敏感度（需要管理权限）

    Args:
        memory_type: 记忆类型
        new_sensitivity: 新的敏感度（0-100）

    Returns:
        JSON格式的更新结果
    """
    ctx = runtime.context if runtime else None

    try:
        if memory_type not in _system.sensitivity_map:
            return json.dumps({
                "error": f"记忆类型 '{memory_type}' 不存在"
            }, ensure_ascii=False, indent=2)

        old_sensitivity = _system.sensitivity_map[memory_type]
        _system.sensitivity_map[memory_type] = new_sensitivity

        return json.dumps({
            "success": True,
            "memory_type": memory_type,
            "old_sensitivity": old_sensitivity,
            "new_sensitivity": new_sensitivity,
            "message": f"记忆类型 '{memory_type}' 的敏感度已从 {old_sensitivity} 更新为 {new_sensitivity}"
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"更新敏感度失败: {str(e)}"
        }, ensure_ascii=False, indent=2)
