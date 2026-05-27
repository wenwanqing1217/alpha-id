"""Alpha-ID 用户身份管理工具（LangGraph 工具层）"""
import bcrypt
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import asdict
from langchain.tools import tool, ToolRuntime
from coze_coding_utils.runtime_ctx.context import new_context

from core.user_identity import UserIdentityManager, UserProfile


# 全局管理器实例
_manager = UserIdentityManager()


@tool
def register_alpha_id(
    device_fingerprint: str,
    is_founder: bool = False,
    founder_code: Optional[str] = None,
    runtime: ToolRuntime = None
) -> str:
    """
    注册Alpha-ID用户

    Args:
        device_fingerprint: 设备指纹
        is_founder: 是否创始人（默认False）
        founder_code: 创始人验证码（创始人注册时需要）

    Returns:
        JSON格式的注册结果，包含：
        - success: 是否成功
        - message: 消息
        - alpha_id: 分配的Alpha-ID编号
        - user_id: 内部用户ID
        - is_founder: 是否创始人
    """
    try:
        result = _manager.register_user(device_fingerprint, is_founder, founder_code)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"注册失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
def get_alpha_id_profile(alpha_id: str, runtime: ToolRuntime = None) -> str:
    """
    获取Alpha-ID用户档案

    Args:
        alpha_id: Alpha-ID编号

    Returns:
        JSON格式的用户档案
    """
    try:
        profile = _manager.get_user_profile(alpha_id)

        if profile is None:
            return json.dumps({
                "success": False,
                "message": f"用户 {alpha_id} 不存在"
            }, ensure_ascii=False, indent=2)

        return json.dumps({
            "success": True,
            "profile": profile
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"获取档案失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
def sync_device(
    alpha_id: str,
    from_device: str,
    to_device: str,
    runtime: ToolRuntime = None
) -> str:
    """
    跨设备同步

    Args:
        alpha_id: Alpha-ID编号
        from_device: 源设备
        to_device: 目标设备

    Returns:
        JSON格式的同步结果
    """
    try:
        result = _manager.sync_cross_device(alpha_id, from_device, to_device)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"同步失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
def record_user_session(alpha_id: str, runtime: ToolRuntime = None) -> str:
    """
    记录用户会话

    Args:
        alpha_id: Alpha-ID编号

    Returns:
        JSON格式的记录结果
    """
    try:
        result = _manager.record_session(alpha_id)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"记录失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
def get_alpha_id_statistics(runtime: ToolRuntime = None) -> str:
    """
    获取Alpha-ID统计信息

    Returns:
        JSON格式的统计信息，包含：
        - total_users: 总用户数
        - active_users: 活跃用户数
        - founder_registered: 创始人是否已注册
        - founder_alpha_id: 创始人的Alpha-ID
        - next_user_id: 下一个用户的Alpha-ID
    """
    try:
        stats = _manager.get_statistics()
        return json.dumps(stats, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"获取统计失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


# ================== 安全设置工具 ==================

@tool
def check_account_status(alpha_id: str, runtime: ToolRuntime = None) -> str:
    """
    检查账号状态

    Args:
        alpha_id: Alpha-ID编号

    Returns:
        JSON格式的账号状态，包含：
        - success: 是否成功
        - status: 账号状态（locked/active/inactive）
        - message: 状态说明
    """
    try:
        user_profile = _manager.get_user_profile(alpha_id)

        if not user_profile:
            return json.dumps({
                "success": False,
                "message": "用户不存在"
            }, ensure_ascii=False)

        status = user_profile["status"]
        message = {
            "locked": "账号已锁定，请完成安全设置后激活",
            "active": "账号已激活，可以正常使用",
            "inactive": "账号已停用"
        }.get(status, "未知状态")

        return json.dumps({
            "success": True,
            "status": status,
            "message": message,
            "alpha_id": alpha_id
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"检查失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
def setup_security_password(
    alpha_id: str,
    password: str,
    runtime: ToolRuntime = None
) -> str:
    """
    设置安全密码

    Args:
        alpha_id: Alpha-ID编号
        password: 密码（建议至少8位，包含字母和数字）

    Returns:
        JSON格式的设置结果
    """
    try:
        # 简单验证密码强度
        if len(password) < 8:
            return json.dumps({
                "success": False,
                "message": "密码长度至少8位"
            }, ensure_ascii=False, indent=2)

        db = _manager._load_database()

        if alpha_id not in db["users"]:
            return json.dumps({
                "success": False,
                "message": "用户不存在"
            }, ensure_ascii=False)

        # 存储密码（bcrypt 加密）
        user_data = db["users"][alpha_id]
        user_data["password"] = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user_data["password_set_at"] = datetime.now().isoformat()

        db["users"][alpha_id] = user_data
        _manager._save_database(db)

        return json.dumps({
            "success": True,
            "message": "密码设置成功",
            "alpha_id": alpha_id
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"设置失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
def verify_alpha_password(
    alpha_id: str,
    password: str,
    runtime: ToolRuntime = None
) -> str:
    """
    验证安全密码

    Args:
        alpha_id: Alpha-ID编号
        password: 待验证的密码

    Returns:
        JSON格式的验证结果
    """
    try:
        db = _manager._load_database()

        if alpha_id not in db["users"]:
            return json.dumps({
                "success": False,
                "message": "用户不存在"
            }, ensure_ascii=False)

        user_data = db["users"][alpha_id]
        stored_hash = user_data.get("password")

        if not stored_hash:
            return json.dumps({
                "success": False,
                "message": "未设置密码，请先设置安全密码"
            }, ensure_ascii=False, indent=2)

        if bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
            return json.dumps({
                "success": True,
                "message": "密码验证通过",
                "alpha_id": alpha_id
            }, ensure_ascii=False, indent=2)
        else:
            return json.dumps({
                "success": False,
                "message": "密码错误"
            }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"验证失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
def setup_security_questions(
    alpha_id: str,
    question1: str,
    answer1: str,
    question2: str,
    answer2: str,
    runtime: ToolRuntime = None
) -> str:
    """
    设置安全问题

    Args:
        alpha_id: Alpha-ID编号
        question1: 问题1
        answer1: 答案1
        question2: 问题2
        answer2: 答案2

    Returns:
        JSON格式的设置结果
    """
    try:
        db = _manager._load_database()

        if alpha_id not in db["users"]:
            return json.dumps({
                "success": False,
                "message": "用户不存在"
            }, ensure_ascii=False)

        user_data = db["users"][alpha_id]
        user_data["security_questions"] = [
            {"question": question1, "answer": answer1},
            {"question": question2, "answer": answer2}
        ]
        user_data["security_questions_set_at"] = datetime.now().isoformat()

        db["users"][alpha_id] = user_data
        _manager._save_database(db)

        return json.dumps({
            "success": True,
            "message": "安全问题设置成功",
            "alpha_id": alpha_id
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"设置失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
def setup_voice_auth(
    alpha_id: str,
    voice_sample: str,
    runtime: ToolRuntime = None
) -> str:
    """
    设置语音认证

    Args:
        alpha_id: Alpha-ID编号
        voice_sample: 语音样本（模拟，实际项目中应该是音频文件）

    Returns:
        JSON格式的设置结果
    """
    try:
        db = _manager._load_database()

        if alpha_id not in db["users"]:
            return json.dumps({
                "success": False,
                "message": "用户不存在"
            }, ensure_ascii=False)

        user_data = db["users"][alpha_id]
        user_data["voice_auth_enabled"] = True
        user_data["voice_sample"] = voice_sample  # TODO: 实际项目中应该存储声纹特征
        user_data["voice_auth_set_at"] = datetime.now().isoformat()

        db["users"][alpha_id] = user_data
        _manager._save_database(db)

        return json.dumps({
            "success": True,
            "message": "语音认证设置成功",
            "alpha_id": alpha_id
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"设置失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
def activate_account(alpha_id: str, runtime: ToolRuntime = None) -> str:
    """
    激活账号（完成所有安全设置后调用）

    Args:
        alpha_id: Alpha-ID编号

    Returns:
        JSON格式的激活结果
    """
    try:
        db = _manager._load_database()

        if alpha_id not in db["users"]:
            return json.dumps({
                "success": False,
                "message": "用户不存在"
            }, ensure_ascii=False)

        user_data = db["users"][alpha_id]

        # 检查安全设置完成情况
        completed = []
        missing = []

        if "password" in user_data and user_data["password"]:
            completed.append("密码")
        else:
            missing.append("密码")

        if "security_questions" in user_data and user_data["security_questions"]:
            completed.append("安全问题")
        else:
            missing.append("安全问题")

        if "voice_auth_enabled" in user_data and user_data["voice_auth_enabled"]:
            completed.append("语音认证")
        else:
            missing.append("语音认证")

        # 激活要求：至少完成2项安全设置
        if len(completed) < 2:
            return json.dumps({
                "success": False,
                "message": f"请至少完成2项安全设置（已完成：{', '.join(completed) if completed else '无'}，未完成：{', '.join(missing)}）"
            }, ensure_ascii=False, indent=2)

        # 激活账号
        user_data["status"] = "active"
        user_data["activated_at"] = datetime.now().isoformat()

        db["users"][alpha_id] = user_data
        _manager._save_database(db)

        return json.dumps({
            "success": True,
            "message": "账号激活成功！现在可以正式使用Alpha-ID了",
            "alpha_id": alpha_id,
            "activated_at": user_data["activated_at"]
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"激活失败: {str(e)}"
        }, ensure_ascii=False, indent=2)
