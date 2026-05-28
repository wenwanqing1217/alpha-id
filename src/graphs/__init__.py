"""
Alpha-ID 状态机图 —— 大脑运行时状态流转

此模块构建 LangGraph 状态图，管理大脑的状态转换。
当前提供手动路由版本（无需 LangGraph 依赖）。
"""

from typing import Dict, Any, Optional
from enum import Enum


class BrainState(Enum):
    SLEEP = "sleep"
    IDLE = "idle"
    AWAKE = "awake"
    ERROR = "error"


# 允许的状态转换
_TRANSITIONS = {
    BrainState.SLEEP: [BrainState.IDLE, BrainState.AWAKE, BrainState.ERROR],
    BrainState.IDLE:  [BrainState.AWAKE, BrainState.SLEEP, BrainState.ERROR],
    BrainState.AWAKE: [BrainState.IDLE, BrainState.SLEEP, BrainState.ERROR],
    BrainState.ERROR: [BrainState.SLEEP, BrainState.IDLE],
}


def validate_transition(from_state: BrainState, to_state: BrainState) -> bool:
    """校验状态转换是否合法"""
    return to_state in _TRANSITIONS.get(from_state, [])


def get_next_state(state: Dict[str, Any]) -> str:
    """
    根据当前状态和输入，决定下一个状态。

    这是状态机的"路由中心"——根据条件判断走哪条边。
    未来可接入 LangGraph 的 ConditionEdge。
    """
    current = BrainState(state.get("state", "sleep"))
    error = state.get("error")
    message = state.get("message")
    now = state.get("current_time", 0)
    last_active = state.get("last_active_time", 0)
    settings = state.get("settings", {})

    # 异常优先
    if error:
        return "error"

    if current == BrainState.SLEEP:
        # 休眠态：有消息或定时唤醒 → awake
        if message:
            return "awake"
        if settings.get("wake_hours"):
            # 检查是否在唤醒时间窗口内
            pass  # 简化处理
        return "sleep"

    elif current == BrainState.IDLE:
        # 空闲态：有消息 → awake；超时 → sleep
        if message:
            return "awake"
        idle_timeout = settings.get("sleep_timeout", 1800)
        if now - last_active > idle_timeout:
            return "sleep"
        return "idle"

    elif current == BrainState.AWAKE:
        # 活跃态：处理完消息 → idle；超时 → sleep
        idle_timeout = settings.get("idle_timeout", 300)
        if now - last_active > idle_timeout:
            return "idle"
        return "awake"

    elif current == BrainState.ERROR:
        # 异常态：手动恢复 → sleep
        if state.get("recover"):
            return "sleep"
        return "error"

    return current.value


def create_initial_state(alpha_id: str) -> Dict[str, Any]:
    """创建初始状态"""
    return {
        "alpha_id": alpha_id,
        "state": "sleep",
        "message": None,
        "error": None,
        "output": "",
        "result": {},
        "last_active_time": 0,
        "current_time": 0,
        "error_log": [],
        "pending_requests": 0,
        "settings": {
            "idle_timeout": 300,
            "sleep_timeout": 1800,
            "auto_reply": False,
        },
    }
