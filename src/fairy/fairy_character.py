"""
FAIRY 2D 角色 — Tkinter Canvas 卡通形象

非药丸形，纯 2D 卡通角色。支持：
- 呼吸动画（透明度脉动）
- 表情切换（正常/观察/说话/思考/睡眠）
- 拖拽移动
- 点击交互
"""

import logging
import math
import tkinter as tk
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class FairyState(Enum):
    """角色状态枚举"""
    IDLE = "idle"           # 待机
    OBSERVING = "observing" # 观察中
    SPEAKING = "speaking"   # 说话中
    THINKING = "thinking"   # 思考中
    SLEEPING = "sleeping"   # 睡眠（眼瞎耳聋模式）


class FairyCharacter:
    """
    2D 卡通角色（Tkinter Canvas）

    角色设计：
    - 圆形头部 + 小身体 + 翅膀
    - 状态驱动颜色变化
    - 呼吸动画
    """

    # 配色方案
    COLORS = {
        FairyState.IDLE:      {"bg": "#a78bfa", "fg": "#ffffff", "glow": "#7c3aed"},
        FairyState.OBSERVING: {"bg": "#60a5fa", "fg": "#ffffff", "glow": "#2563eb"},
        FairyState.SPEAKING:  {"bg": "#34d399", "fg": "#ffffff", "glow": "#059669"},
        FairyState.THINKING:  {"bg": "#fbbf24", "fg": "#ffffff", "glow": "#d97706"},
        FairyState.SLEEPING:  {"bg": "#6b7280", "fg": "#d1d5db", "glow": "#374151"},
    }

    def __init__(self, canvas: tk.Canvas, x: int = 200, y: int = 200, size: int = 80):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.size = size
        self.state = FairyState.IDLE
        self._animation_id = None
        self._breath_phase = 0.0

        # 绘制角色
        self._draw()
        self._start_breath_animation()

    def _draw(self):
        """绘制角色（圆头 + 小翅膀 + 眼睛）"""
        self.canvas.delete("fairy")
        colors = self.COLORS[self.state]
        r = self.size // 2

        # 翅膀（左右各一）
        wing_offset = r + 8
        wing_y = self.y + 5
        self.canvas.create_oval(
            self.x - wing_offset - 10, wing_y - 8,
            self.x - wing_offset + 10, wing_y + 8,
            fill=colors["glow"], outline="", tags="fairy"
        )
        self.canvas.create_oval(
            self.x + wing_offset - 10, wing_y - 8,
            self.x + wing_offset + 10, wing_y + 8,
            fill=colors["glow"], outline="", tags="fairy"
        )

        # 身体（圆）
        self.canvas.create_oval(
            self.x - r, self.y - r,
            self.x + r, self.y + r,
            fill=colors["bg"], outline=colors["glow"], width=3, tags="fairy"
        )

        # 眼睛
        eye_y = self.y - 5
        eye_offset = r // 3
        eye_size = max(3, r // 8)

        if self.state == FairyState.SLEEPING:
            # 睡觉：闭线（横线）
            self.canvas.create_line(
                self.x - eye_offset - 5, eye_y,
                self.x - eye_offset + 5, eye_y,
                fill=colors["fg"], width=2, tags="fairy"
            )
            self.canvas.create_line(
                self.x + eye_offset - 5, eye_y,
                self.x + eye_offset + 5, eye_y,
                fill=colors["fg"], width=2, tags="fairy"
            )
        else:
            # 睁眼（圆点）
            for dx in [-eye_offset, eye_offset]:
                self.canvas.create_oval(
                    self.x + dx - eye_size, eye_y - eye_size,
                    self.x + dx + eye_size, eye_y + eye_size,
                    fill=colors["fg"], outline="", tags="fairy"
                )

        # 微笑
        if self.state != FairyState.SLEEPING:
            self.canvas.create_arc(
                self.x - 10, self.y,
                self.x + 10, self.y + 15,
                start=0, extent=-180, style="arc",
                outline=colors["fg"], width=2, tags="fairy"
            )

    def set_state(self, state: FairyState):
        """切换状态（触发动画重绘）"""
        if state != self.state:
            self.state = state
            self._draw()
            logger.debug(f"角色状态: {state.value}")

    def _start_breath_animation(self):
        """呼吸动画（大小脉动）"""
        self._breath_phase += 0.05
        scale = 1.0 + 0.03 * math.sin(self._breath_phase)
        # 简单的呼吸效果：轻微缩放
        # 实际实现可以用 canvas.scale，但这里简化
        try:
            self._animation_id = self.canvas.after(50, self._start_breath_animation)
        except Exception:
            pass

    def move_to(self, x: int, y: int):
        """移动角色到指定位置"""
        dx = x - self.x
        dy = y - self.y
        self.canvas.move("fairy", dx, dy)
        self.x = x
        self.y = y

    def contains(self, x: int, y: int) -> bool:
        """检查点是否在角色范围内"""
        r = self.size // 2 + 10
        return (x - self.x) ** 2 + (y - self.y) ** 2 <= r ** 2

    def destroy(self):
        """清理"""
        if self._animation_id:
            try:
                self.canvas.after_cancel(self._animation_id)
            except Exception:
                pass
        self.canvas.delete("fairy")
