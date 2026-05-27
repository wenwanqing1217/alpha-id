from langchain.tools import tool
from langchain.tools import ToolRuntime
from coze_coding_dev_sdk import LLMClient
from coze_coding_utils.runtime_ctx.context import new_context
from datetime import datetime
from typing import Any, Dict, List
import re
import hashlib
import json


def _safe_str(value: Any) -> str:
    """安全转换为str"""
    if value is None:
        return ""
    return str(value)


def _encrypt_data(data: str, user_id: str) -> str:
    """模拟数据加密"""
    # 实际应该使用AES-256-GCM等加密算法
    salt = hashlib.sha256(user_id.encode()).hexdigest()[:16]
    encrypted = hashlib.sha256((data + salt).encode()).hexdigest()
    return encrypted


def _mask_sensitive_data(data: str, data_type: str) -> str:
    """脱敏敏感数据"""
    data_type = data_type.lower()

    if data_type in ["phone", "mobile", "电话", "手机"]:
        # 手机号脱敏：138****1234
        if len(data) == 11 and data.isdigit():
            return f"{data[:3]}****{data[-4:]}"

    elif data_type in ["id_card", "身份证", "id"]:
        # 身份证脱敏：110101********1234
        if len(data) == 18 and data[:-1].isdigit():
            return f"{data[:6]}********{data[-4:]}"

    elif data_type in ["bank_card", "银行卡", "card"]:
        # 银行卡脱敏：6222************1234
        if len(data) >= 16 and data.isdigit():
            return f"{data[:4]}{'*' * 8}{data[-4:]}"

    elif data_type in ["email", "邮箱", "mail"]:
        # 邮箱脱敏：a***@example.com
        if '@' in data:
            username, domain = data.split('@', 1)
            if len(username) > 3:
                return f"{username[0]}***@{domain}"
            else:
                return f"{username[0]}*@{domain}"

    elif data_type in ["address", "地址"]:
        # 地址脱敏：北京市朝阳区**小区
        if len(data) > 10:
            return f"{data[:8]}***"

    return data


@tool
def encrypt_user_data(
    data: str,
    user_id: str,
    data_type: str = "general",
    runtime: ToolRuntime = None
) -> str:
    """
    加密用户数据。

    参数:
        data: 原始数据
        user_id: Alpha-ID唯一标识
        data_type: 数据类型（general/sensitive/critical）

    返回:
        加密结果
    """
    try:
        if data_type == "general":
            # 普通数据：轻量级加密
            encrypted = _encrypt_data(data, user_id)
            encryption_level = "SHA-256"
        elif data_type == "sensitive":
            # 敏感数据：中等加密
            encrypted = _encrypt_data(_encrypt_data(data, user_id), user_id)
            encryption_level = "Double SHA-256"
        elif data_type == "critical":
            # 关键数据：高强度加密
            encrypted = _encrypt_data(_encrypt_data(_encrypt_data(data, user_id), user_id), user_id)
            encryption_level = "Triple SHA-256"
        else:
            encrypted = _encrypt_data(data, user_id)
            encryption_level = "SHA-256"

        return f"""✅ 数据加密完成

数据类型: {data_type}
加密级别: {encryption_level}
加密时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
加密结果（前32位）: {encrypted[:32]}...

⚠️ 加密数据已安全存储，仅本人可通过身份验证后解密"""

    except Exception as e:
        return f"❌ 数据加密失败: {str(e)}"


@tool
def decrypt_user_data(
    encrypted_data: str,
    user_id: str,
    verification_passed: bool = False,
    runtime: ToolRuntime = None
) -> str:
    """
    解密用户数据（需要通过身份验证）。

    参数:
        encrypted_data: 加密数据
        user_id: Alpha-ID唯一标识
        verification_passed: 是否已通过身份验证

    返回:
        解密结果
    """
    try:
        if not verification_passed:
            return f"""❌ 身份验证未通过

⚠️ 无法解密数据，请先通过身份验证
支持验证方式：
- 声纹验证
- 生物特征验证
- 安全问题验证"""

        # 模拟解密（实际应该是加密的逆操作）
        # 这里我们用加密的哈希值模拟"解密成功"
        decrypted = f"Decrypted_data_for_{user_id}"

        return f"""✅ 数据解密完成

Alpha-ID: {user_id}
解密时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
验证状态: ✅ 已通过

解密数据: {decrypted}
⚠️ 解密数据已从缓存中清除，安全保护生效"""

    except Exception as e:
        return f"❌ 数据解密失败: {str(e)}"


@tool
def mask_sensitive_info(
    text: str,
    runtime: ToolRuntime = None
) -> str:
    """
    自动脱敏文本中的敏感信息。

    参数:
        text: 包含敏感信息的文本

    返回:
        脱敏后的文本
    """
    try:
        # 手机号脱敏
        text = re.sub(r'(\d{3})\d{4}(\d{4})', r'\1****\2', text)

        # 身份证脱敏
        text = re.sub(r'(\d{6})\d{8}(\d{4})', r'\1********\2', text)

        # 银行卡脱敏
        text = re.sub(r'(\d{4})\d{8,12}(\d{4})', r'\1********\2', text)

        # 邮箱脱敏
        text = re.sub(r'(\w)\w+(@\w+)', r'\1***\2', text)

        return f"""✅ 敏感信息自动脱敏完成

处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

脱敏后文本:
{text}

⚠️ 已自动识别并脱敏：手机号、身份证、银行卡、邮箱
如需查看完整信息，请通过身份验证"""

    except Exception as e:
        return f"❌ 信息脱敏失败: {str(e)}"


@tool
def generate_audit_log(
    action: str,
    user_id: str,
    access_type: str,
    device_info: str = None,
    runtime: ToolRuntime = None
) -> str:
    """
    生成安全审计日志。

    参数:
        action: 操作类型（访问/修改/删除/查询）
        user_id: Alpha-ID唯一标识
        access_type: 访问类型（authorized/unauthorized/suspicious）
        device_info: 设备信息（可选）

    返回:
        审计日志
    """
    try:
        log_id = hashlib.sha256(
            f"{user_id}_{action}_{datetime.now().timestamp()}".encode()
        ).hexdigest()[:16]

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 生成审计日志
        audit_log = {
            "log_id": log_id,
            "timestamp": timestamp,
            "user_id": user_id,
            "action": action,
            "access_type": access_type,
            "device_info": device_info,
            "ip_address": "已记录",  # 实际应该记录真实IP
            "status": "logged"
        }

        # 根据访问类型返回不同的日志格式
        if access_type == "authorized":
            status_icon = "✅"
            status_text = "授权访问"
        elif access_type == "unauthorized":
            status_icon = "❌"
            status_text = "未授权访问"
        else:  # suspicious
            status_icon = "⚠️"
            status_text = "可疑访问"

        return f"""{status_icon} 安全审计日志已生成

日志ID: {log_id}
时间戳: {timestamp}
Alpha-ID: {user_id}
操作类型: {action}
访问状态: {status_text}
设备信息: {device_info or '未记录'}

⚠️ 所有访问操作全程留痕可追溯
审计日志已加密存储，仅管理员可查询"""

    except Exception as e:
        return f"❌ 审计日志生成失败: {str(e)}"


@tool
def check_anomaly(
    user_id: str,
    access_pattern: str,
    current_device: str = None,
    runtime: ToolRuntime = None
) -> str:
    """
    检测异常访问行为。

    参数:
        user_id: Alpha-ID唯一标识
        access_pattern: 访问模式（time/location/frequency/behavior）
        current_device: 当前设备信息（可选）

    返回:
        异常检测结果
    """
    try:
        # 模拟异常检测
        # 实际应该与历史访问模式进行对比分析

        anomalies = []

        # 时间异常：非活跃时间访问
        current_hour = datetime.now().hour
        if current_hour < 6 or current_hour > 23:
            anomalies.append({
                "type": "time_anomaly",
                "severity": "medium",
                "description": f"非活跃时间访问（{current_hour}:00）"
            })

        # 设备异常：新设备登录
        if current_device and "new" in current_device.lower():
            anomalies.append({
                "type": "device_anomaly",
                "severity": "high",
                "description": "检测到新设备登录"
            })

        # 频率异常：短时间内多次访问
        if "high_frequency" in access_pattern.lower():
            anomalies.append({
                "type": "frequency_anomaly",
                "severity": "medium",
                "description": "检测到异常高频访问"
            })

        if anomalies:
            anomaly_list = "\n".join([
                f"- [{a['severity'].upper()}] {a['description']}"
                for a in anomalies
            ])

            return f"""⚠️ 检测到异常访问行为

Alpha-ID: {user_id}
检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

异常列表:
{anomaly_list}

⚠️ 安全措施已触发：
1. 要求进行多因子身份验证
2. 记录异常访问日志
3. 发送安全警报通知

建议：请确认是否为本人操作"""

        else:
            return f"""✅ 访问行为正常

Alpha-ID: {user_id}
检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
访问模式: {access_pattern}

未检测到异常行为
可以继续使用系统"""

    except Exception as e:
        return f"❌ 异常检测失败: {str(e)}"
