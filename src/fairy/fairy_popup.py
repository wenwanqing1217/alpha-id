"""
NURO 通知系统 — 气泡/弹幕/Toast

通知类型：
- Bubble: 角色旁边的对话气泡
- Barrage: 屏幕顶部弹幕（非侵入式）
- Toast: Windows 系统通知
"""

import logging
import tkinter as tk
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class PopupType(Enum):
    BUBBLE = "bubble"
    BARRAGE = "barrage"
    TOAST = "toast"


class FairyPopup:
    """
    通知系统

    支持三种通知方式，按侵入性递增：
    1. Bubble - 角色旁边气泡（最轻）
    2. Barrage - 屏幕顶部弹幕（中等）
    3. Toast - Windows 通知（最重）
    """

    def __init__(self, ball_window: Optional[tk.Tk] = None, default_type: PopupType = PopupType.BUBBLE):
        self.ball = ball_window
        self.default_type = default_type
        self._bubble_windows = []

    def show(self, message: str, popup_type: Optional[PopupType] = None,
             duration: int = 5000, x: int = 0, y: int = 0):
        """
        显示通知

        Args:
            message: 消息文本
            popup_type: 通知类型，默认 Bubble
            duration: 显示时长（毫秒）
            x, y: 气泡位置
        """
        t = popup_type or self.default_type
        if t == PopupType.BUBBLE:
            self._show_bubble(message, duration, x, y)
        elif t == PopupType.BARRAGE:
            self._show_barrage(message, duration)
        elif t == PopupType.TOAST:
            self._show_toast(message)
        else:
            logger.warning(f"未知通知类型: {t}")

    def _show_bubble(self, message: str, duration: int, x: int, y: int):
        """角色旁边的气泡"""
        if not self.ball:
            # 无父窗口时用独立气泡
            self._show_floating_bubble(message, duration, x, y)
            return

        try:
            bubble = tk.Label(
                self.ball,
                text=message,
                bg="#f3f4f6",
                fg="#1f2937",
                font=("微软雅黑", 10),
                padx=10, pady=5,
                wraplength=200,
                borderwidth=1,
                relief="solid"
            )
            bubble.place(x=x, y=y)
            # 定时消失
            self.ball.after(duration, bubble.destroy)
        except Exception as e:
            logger.error(f"气泡显示失败: {e}")

    def _show_floating_bubble(self, message: str, duration: int, x: int, y: int):
        """独立气泡窗口"""
        try:
            win = tk.Tk()
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.95)
            win.geometry(f"+{x}+{y}")

            label = tk.Label(
                win, text=message,
                bg="#f3f4f6", fg="#1f2937",
                font=("微软雅黑", 10),
                padx=10, pady=5,
                wraplength=200,
                borderwidth=1, relief="solid"
            )
            label.pack()

            win.after(duration, win.destroy)
            self._bubble_windows.append(win)
        except Exception as e:
            logger.error(f"浮动气泡失败: {e}")

    def _show_barrage(self, message: str, duration: int):
        """屏幕顶部弹幕"""
        try:
            win = tk.Tk()
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.9)
            win.configure(bg="#1f2937")

            # 顶部居中
            screen_w = win.winfo_screenwidth()
            win.geometry(f"+{screen_w // 2 - 150}+30")

            label = tk.Label(
                win, text=message,
                bg="#1f2937", fg="#f9fafb",
                font=("微软雅黑", 11),
                padx=15, pady=8
            )
            label.pack()

            win.after(duration, win.destroy)
        except Exception as e:
            logger.error(f"弹幕显示失败: {e}")

    def _show_toast(self, message: str):
        """Windows Toast 通知"""
        try:
            from win10toast import Notifier
            toaster = Notifier()
            toaster.show_toast("NURO", message, duration=5, threaded=True)
        except ImportError:
            # fallback to barrage
            logger.info("win10toast 未安装，fallback 到弹幕")
            self._show_barrage(message, 5000)
        except Exception as e:
            logger.error(f"Toast 失败: {e}")
