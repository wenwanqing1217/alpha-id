import hashlib
from datetime import datetime, timedelta
from typing import Any

from tools.tool_decorator import ToolRuntime, tool


def _safe_str(value: Any) -> str:
    """安全转换为str"""
    if value is None:
        return ""
    return str(value)


@tool
def lock_account(
    user_id: str, reason: str, lock_duration: int = 30, notify_user: bool = True, runtime: ToolRuntime = None
) -> str:
    """
    锁定用户账户（安全措施）。

    参数:
        user_id: Alpha-ID唯一标识
        reason: 锁定原因
        lock_duration: 锁定时长（分钟，默认30）
        notify_user: 是否通知用户

    返回:
        锁定结果
    """
    try:
        lock_id = hashlib.sha256(f"{user_id}_{reason}_{datetime.now().timestamp()}".encode()).hexdigest()[:16]

        lock_time = datetime.now()
        unlock_time = lock_time + timedelta(minutes=lock_duration)

        {
            "lock_id": lock_id,
            "user_id": user_id,
            "reason": reason,
            "locked_at": lock_time.isoformat(),
            "unlock_at": unlock_time.isoformat(),
            "duration_minutes": lock_duration,
            "status": "locked",
        }

        notification = ""
        if notify_user:
            notification = f"""
📱 安全通知已发送：
通知类型: 账户锁定通知
接收人: {user_id}
通知内容: 您的账户因'{reason}'已被临时锁定"""

        return f"""🔒 账户已锁定

锁定ID: {lock_id}
Alpha-ID: {user_id}
锁定原因: {reason}
锁定时间: {lock_time.strftime("%Y-%m-%d %H:%M:%S")}
解锁时间: {unlock_time.strftime("%Y-%m-%d %H:%M:%S")}
锁定时长: {lock_duration} 分钟

⚠️ 在锁定期间，所有访问将被拒绝{notification}

如需紧急解锁，请联系管理员并提供锁定ID"""

    except Exception as e:
        return f"❌ 账户锁定失败: {str(e)}"


@tool
def generate_security_report(
    user_id: str, report_type: str = "summary", time_range: str = "week", runtime: ToolRuntime = None
) -> str:
    """
    生成安全报告。

    参数:
        user_id: Alpha-ID唯一标识
        report_type: 报告类型（summary/detailed/audit）
        time_range: 时间范围（day/week/month/year）

    返回:
        安全报告
    """
    try:
        report_id = hashlib.sha256(f"{user_id}_{report_type}_{datetime.now().timestamp()}".encode()).hexdigest()[:16]

        # 模拟生成安全报告
        if report_type == "summary":
            report_content = """📊 安全状况摘要

✅ 整体安全评级: A级（优秀）
✅ 身份验证成功率: 99.8%
✅ 异常访问检测: 0次
✅ 数据加密状态: 全部加密
✅ 设备绑定状态: 3台设备"""

        elif report_type == "detailed":
            report_content = """📋 详细安全报告

身份验证统计:
- 声纹验证: 45次，成功率99.2%
- 生物特征验证: 23次，成功率100%
- 安全问题验证: 12次，成功率95.8%
- 输入行为校验: 78次，成功率99.6%

访问统计:
- 总访问次数: 158次
- 授权访问: 157次
- 未授权访问: 1次（已拦截）
- 可疑访问: 0次

设备管理:
- 已绑定设备: 3台
- 活跃设备: 2台
- 未知设备: 0台
- 设备异常: 0次"""

        elif report_type == "audit":
            report_content = """🔍 审计日志报告

关键访问记录:
1. 2025-06-18 10:30:15 - 授权访问 - 设备A - 声纹验证
2. 2025-06-17 18:45:22 - 授权访问 - 设备B - 生物特征验证
3. 2025-06-17 14:20:08 - 授权访问 - 设备A - 安全问题验证
4. 2025-06-16 09:15:33 - 未授权访问 - 未知设备 - 已拦截

异常事件:
- 无异常事件记录

安全建议:
1. 定期更新安全问题答案
2. 启用多因子身份验证
3. 定期检查设备绑定列表"""

        else:
            report_content = "报告类型不支持"

        return f"""✅ 安全报告已生成

报告ID: {report_id}
Alpha-ID: {user_id}
报告类型: {report_type.upper()}
时间范围: {time_range}
生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

{report_content}

⚠️ 报告已加密存储，仅本人可查看"""

    except Exception as e:
        return f"❌ 安全报告生成失败: {str(e)}"


@tool
def set_security_level(user_id: str, level: str, require_mfa: bool = True, runtime: ToolRuntime = None) -> str:
    """
    设置安全级别。

    参数:
        user_id: Alpha-ID唯一标识
        level: 安全级别（low/medium/high/ultra）
        require_mfa: 是否要求多因子验证

    返回:
        设置结果
    """
    try:
        level_requirements = {
            "low": {
                "name": "低安全级别",
                "required_factors": 1,
                "description": "仅需要单一验证方式，适用于低风险操作",
                "features": ["单因子验证", "基础加密", "日志记录"],
            },
            "medium": {
                "name": "中安全级别",
                "required_factors": 2,
                "description": "需要双重验证，适用于常规操作",
                "features": ["双因子验证", "标准加密", "异常检测", "日志记录"],
            },
            "high": {
                "name": "高安全级别",
                "required_factors": 3,
                "description": "需要三重验证，适用于敏感操作",
                "features": ["三因子验证", "高强度加密", "实时监控", "异常预警", "完整审计"],
            },
            "ultra": {
                "name": "极高安全级别",
                "required_factors": 4,
                "description": "需要四重验证，适用于关键操作",
                "features": ["四因子验证", "军事级加密", "持续监控", "即时预警", "完整审计", "硬件安全模块"],
            },
        }

        if level not in level_requirements:
            return f"❌ 无效的安全级别: {level}"

        level_info = level_requirements[level]

        mfa_status = "✅ 已启用" if require_mfa else "❌ 未启用"

        return f"""✅ 安全级别已设置

Alpha-ID: {user_id}
安全级别: {level_info["name"]}
所需验证因子: {level_info["required_factors"]} 个
多因子验证: {mfa_status}

启用功能:
{chr(10).join(f"• {feature}" for feature in level_info["features"])}

说明: {level_info["description"]}

⚠️ 安全级别设置已生效，后续访问将按照新标准执行"""

    except Exception as e:
        return f"❌ 安全级别设置失败: {str(e)}"


@tool
def revoke_device_access(user_id: str, device_id: str, reason: str, runtime: ToolRuntime = None) -> str:
    """
    撤销设备访问权限。

    参数:
        user_id: Alpha-ID唯一标识
        device_id: 设备ID或设备名称
        reason: 撤销原因

    返回:
        撤销结果
    """
    try:
        revoke_id = hashlib.sha256(f"{user_id}_{device_id}_{datetime.now().timestamp()}".encode()).hexdigest()[:16]

        return f"""✅ 设备访问权限已撤销

撤销ID: {revoke_id}
Alpha-ID: {user_id}
设备ID: {device_id}
撤销原因: {reason}
撤销时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

⚠️ 该设备已无法访问您的Alpha-ID账户
如需恢复访问，请在设备上重新进行身份验证

建议操作：
1. 检查该设备是否仍在您控制下
2. 确认是否为本人操作
3. 如怀疑账户被入侵，请立即修改安全设置"""

    except Exception as e:
        return f"❌ 设备访问权限撤销失败: {str(e)}"


@tool
def zero_knowledge_proof(
    user_id: str, statement: str, proof_type: str = "identity", runtime: ToolRuntime = None
) -> str:
    """
    零知识证明（在不泄露任何信息的情况下验证身份）。

    参数:
        user_id: Alpha-ID唯一标识
        statement: 待验证的声明
        proof_type: 证明类型（identity/ownership/authenticity）

    返回:
        证明结果
    """
    try:
        # 模拟零知识证明
        # 实际应该使用zk-SNARKs或zk-STARKs等技术

        proof_id = hashlib.sha256(f"{user_id}_{statement}_{datetime.now().timestamp()}".encode()).hexdigest()[:16]

        proof_valid = len(statement) > 5

        if proof_valid:
            return f"""✅ 零知识证明验证通过

证明ID: {proof_id}
Alpha-ID: {user_id}
验证声明: {statement}
证明类型: {proof_type}
验证时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

验证结果: ✅ 有效
信息泄露: 0字节
隐私保护: 100%

⚠️ 在不泄露任何信息的情况下，已成功验证您的身份
这是未来Web3.0时代的核心安全技术"""

        else:
            return f"""❌ 零知识证明验证失败

证明ID: {proof_id}
Alpha-ID: {user_id}
验证声明: {statement}
证明类型: {proof_type}

验证结果: ❌ 无效
失败原因: 声明格式不正确或证明生成失败"""

    except Exception as e:
        return f"❌ 零知识证明失败: {str(e)}"
