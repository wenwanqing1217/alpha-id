"""
Alpha-ID 状态机 —— LangGraph 节点定义

大脑状态图：
  SLEEP → IDLE → AWAKE → IDLE → SLEEP
    ↓       ↓       ↓
  ERROR ← ERROR ← ERROR
  ERROR → SLEEP (恢复)
"""

from typing import Dict, Any, Optional


# ── 状态节点处理函数 ──

def sleep_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    休眠节点：低功耗，仅响应唤醒信号。
    """
    return {
        **state,
        "state": "sleep",
        "output": "大脑处于休眠状态",
        "auto_reply": state.get("settings", {}).get("auto_reply", False),
    }


def idle_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    空闲待机节点：低功耗监听外部请求，可被唤醒。
    """
    return {
        **state,
        "state": "idle",
        "output": "大脑空闲待机中，等待唤醒...",
        "pending_requests": state.get("pending_requests", 0),
    }


def awake_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    活跃节点：处理消息、请求、自主学习。
    根据输入消息类型路由到不同的处理逻辑。
    """
    msg_type = state.get("message", {}).get("msg_type", "")
    result = {}

    if msg_type == "chat":
        result = {"handled": True, "action": "process_chat"}
    elif msg_type == "friend_request":
        result = {"handled": True, "action": "process_friend_request"}
    elif msg_type == "profile_query":
        result = {"handled": True, "action": "process_profile_query"}
    elif msg_type == "ping":
        result = {"handled": True, "action": "pong"}
    else:
        result = {"handled": False, "action": "unknown_message"}

    return {
        **state,
        "state": "awake",
        "output": f"正在处理 {msg_type} 消息",
        "result": result,
    }


def error_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    异常节点：安全模式，记录错误日志，拒绝服务。
    """
    error_msg = state.get("error", "未知错误")
    return {
        **state,
        "state": "error",
        "output": f"大脑异常: {error_msg}",
        "error_log": state.get("error_log", []) + [error_msg],
    }


# ── 边条件判断函数 ──

def should_transition_to_idle(state: Dict[str, Any]) -> bool:
    """判断是否应转入空闲"""
    last_active = state.get("last_active_time", 0)
    now = state.get("current_time", 0)
    timeout = state.get("settings", {}).get("idle_timeout", 300)
    return (now - last_active) > timeout


def should_transition_to_sleep(state: Dict[str, Any]) -> bool:
    """判断是否应转入休眠"""
    last_active = state.get("last_active_time", 0)
    now = state.get("current_time", 0)
    timeout = state.get("settings", {}).get("sleep_timeout", 1800)
    return (now - last_active) > timeout


def has_new_message(state: Dict[str, Any]) -> bool:
    """判断是否有新消息"""
    return bool(state.get("message"))


def is_error_state(state: Dict[str, Any]) -> bool:
    """判断是否发生异常"""
    return bool(state.get("error"))
