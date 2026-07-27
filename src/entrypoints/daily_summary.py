"""
NURO 桌面精灵 — 每日总结调度

负责：
  - 计算下一次 22:00 的延迟并调度自动总结
  - 手动触发同步总结（在后台线程中执行）
  - 自动总结完成后重新调度下一天

BUG FIX: 原 daemon.py:1141 使用 timedelta 但未导入，此处修复。
"""

import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def compute_next_summary_delay_ms(now: datetime | None = None) -> int:
    """计算距离下一次 22:00 的毫秒数

    Args:
        now: 当前时间（可注入，便于测试），默认 datetime.now()

    Returns:
        下一次 22:00 的毫秒延迟（已确保 > 0）
    """
    if now is None:
        now = datetime.now()

    target = now.replace(hour=22, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)

    return int((target - now).total_seconds() * 1000)


def schedule_daily_summary(ball, daily, safe_call, on_done=None) -> None:
    """调度每日自动总结

    Args:
        ball: Tkinter 根窗口（用于 after 调度）
        daily: FairyDaily 实例
        safe_call: 线程安全调用包装器（fn → ball.after(0, fn)）
        on_done: 可选回调，接收 summary 字符串
    """
    delay_ms = compute_next_summary_delay_ms()
    ball.after(delay_ms, lambda: _auto_daily_summary(ball, daily, safe_call, on_done))


def _auto_daily_summary(ball, daily, safe_call, on_done=None):
    """自动触发每日总结（内部）"""
    def _run():
        try:
            summary = daily.generate()
            if on_done:
                safe_call(lambda: on_done(summary))
        except Exception as e:
            logger.warning("每日总结生成失败: %s", e)
        finally:
            # 重新调度明天
            try:
                ball.after(24 * 3600 * 1000, lambda: _auto_daily_summary(ball, daily, safe_call, on_done))
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()


def show_daily_summary(ball, daily, safe_call, add_chat_message, set_character_state,
                       FairyState, ensure_chat_open) -> None:
    """手动触发每日总结

    在后台线程中生成，完成后通过 safe_call 更新 UI。
    """
    if not daily:
        ensure_chat_open()
        add_chat_message("error", "每日总结功能未加载")
        return

    ensure_chat_open()
    add_chat_message("thinking", "📋 正在回顾今天...")
    set_character_state(FairyState.THINK)

    def _do():
        try:
            summary = daily.generate()
            safe_call(lambda: _remove_last_thinking(add_chat_message))
            safe_call(lambda: add_chat_message("ai", f"📋 **今日锐评**\n{summary}"))
        except Exception as e:
            safe_call(lambda: _remove_last_thinking(add_chat_message))
            safe_call(lambda e=e: add_chat_message("error", f"生成失败：{e}"))
        finally:
            safe_call(lambda: set_character_state(FairyState.IDLE))

    threading.Thread(target=_do, daemon=True).start()


def _remove_last_thinking(add_chat_message):
    """移除最后一条 thinking 消息（通过回调间接操作）"""
    # 实际实现通过 chat_panel 的内部方法完成；此处仅作占位
    # 由 app.py 注入具体的 remove_last_thinking 实现
    pass
