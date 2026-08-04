"""
NURO Ghost — Ghost Platform 幽灵角色（替换原猫娘）

与前端 GhostSprite 保持一致：白色幽灵 + 紫色光晕。
"""

import logging
import math
import tkinter as tk
from enum import Enum

logger = logging.getLogger(__name__)


class FairyState(Enum):
    """角色状态（保持 FairyState 名称兼容旧代码）"""
    IDLE = "idle"
    OBSERVING = "observing"
    SPEAK = "speak"
    THINK = "think"
    LISTEN = "listen"
    HAPPY = "happy"
    WARN = "warn"
    BLIND = "blind"
    SLEEPING = "sleeping"


class FairyCharacter:
    """
    Ghost Platform 幽灵角色（Tkinter Canvas）

    设计：
    - 白色幽灵身体（圆顶 + 波浪底边）
    - 紫色光晕（nebula #8b5cf6）
    - 大眼睛（带高光）
    - 状态驱动颜色和动画
    - 呼吸浮动 + 眨眼
    """

    COLORS = {
        FairyState.IDLE:      {"body": "#ffffff", "glow": "#8b5cf6", "eye": "#1e1b4b", "cheek": "#c4b5fd"},
        FairyState.OBSERVING: {"body": "#ffffff", "glow": "#38bdf8", "eye": "#0c4a6e", "cheek": "#7dd3fc"},
        FairyState.SPEAK:     {"body": "#ffffff", "glow": "#10b981", "eye": "#064e3b", "cheek": "#6ee7b7"},
        FairyState.THINK:     {"body": "#f5f3ff", "glow": "#f59e0b", "eye": "#78350f", "cheek": "#fcd34d"},
        FairyState.LISTEN:    {"body": "#ffffff", "glow": "#3b82f6", "eye": "#1e3a5f", "cheek": "#93c5fd"},
        FairyState.HAPPY:     {"body": "#ffffff", "glow": "#10b981", "eye": "#064e3b", "cheek": "#6ee7b7"},
        FairyState.WARN:      {"body": "#fef3c7", "glow": "#ef4444", "eye": "#7f1d1d", "cheek": "#fca5a5"},
        FairyState.BLIND:     {"body": "#e5e7eb", "glow": "#6b7280", "eye": "#9ca3af", "cheek": "#d1d5db"},
        FairyState.SLEEPING:  {"body": "#e5e7eb", "glow": "#6b7280", "eye": "#9ca3af", "cheek": "#d1d5db"},
    }

    def __init__(self, canvas: tk.Canvas, x: int = 200, y: int = 200, size: int = 80):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.size = size
        self.state = FairyState.IDLE
        self._animation_id = None
        self._breath_phase = 0.0
        self._blink_counter = 0
        self._mouth_phase = 0

        self._draw()
        self._start_breath_animation()

    def _draw(self):
        """绘制 Ghost 幽灵"""
        self.canvas.delete("fairy")
        colors = self.COLORS[self.state]
        s = self.size
        cx, cy = self.x, self.y

        # ── 光晕 ──
        glow_r = s * 0.8
        self.canvas.create_oval(
            cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r,
            fill="", outline=colors["glow"], width=1, tags="fairy"
        )
        glow_r2 = s * 1.1
        self.canvas.create_oval(
            cx - glow_r2, cy - glow_r2, cx + glow_r2, cy + glow_r2,
            fill="", outline=colors["glow"], width=0.5, tags="fairy"
        )

        # ── 身体（圆顶 + 波浪底边）──
        body_top = cy - s * 0.55
        body_bottom = cy + s * 0.5
        body_width = s * 0.55
        wave_w = body_width * 2 / 3
        wave_h = s * 0.1

        body_coords = [
            cx - body_width, cy + s * 0.1,
            cx - body_width * 0.7, body_top,
            cx, body_top - s * 0.05,
            cx + body_width * 0.7, body_top,
            cx + body_width, cy + s * 0.1,
            cx + body_width, body_bottom,
            cx + body_width - wave_w * 0.3, body_bottom - wave_h,
            cx + body_width - wave_w * 0.6, body_bottom + wave_h * 0.5,
            cx + body_width - wave_w, body_bottom - wave_h * 0.8,
            cx + body_width - wave_w * 1.3, body_bottom + wave_h * 0.3,
            cx - body_width, body_bottom,
        ]
        self.canvas.create_polygon(
            body_coords,
            fill=colors["body"], outline=colors["glow"], width=2, tags="fairy"
        )

        # ── 眼睛 ──
        eye_r = s * 0.12
        eye_y = cy - s * 0.1
        eye_spacing = s * 0.2

        if self.state in (FairyState.SLEEPING, FairyState.BLIND):
            for dx in [-eye_spacing, eye_spacing]:
                self.canvas.create_arc(
                    cx + dx - eye_r, eye_y - eye_r * 0.5,
                    cx + dx + eye_r, eye_y + eye_r * 0.5,
                    start=0, extent=180, style="arc",
                    outline=colors["eye"], width=2, tags="fairy"
                )
        elif self.state == FairyState.THINK:
            for dx in [-eye_spacing, eye_spacing]:
                self.canvas.create_oval(
                    cx + dx - eye_r, eye_y - eye_r,
                    cx + dx + eye_r, eye_y + eye_r,
                    fill=colors["eye"], outline="", tags="fairy"
                )
                hr = eye_r * 0.3
                self.canvas.create_oval(
                    cx + dx + eye_r * 0.2 - hr, eye_y - eye_r * 0.3 - hr,
                    cx + dx + eye_r * 0.2 + hr, eye_y - eye_r * 0.3 + hr,
                    fill="white", outline="", tags="fairy"
                )
        else:
            for dx in [-eye_spacing, eye_spacing]:
                if self._should_blink():
                    self.canvas.create_line(
                        cx + dx - eye_r, eye_y, cx + dx + eye_r, eye_y,
                        fill=colors["eye"], width=2, tags="fairy"
                    )
                else:
                    self.canvas.create_oval(
                        cx + dx - eye_r, eye_y - eye_r * 1.3,
                        cx + dx + eye_r, eye_y + eye_r * 1.3,
                        fill="white", outline=colors["eye"], width=1, tags="fairy"
                    )
                    pr = eye_r * 0.7
                    self.canvas.create_oval(
                        cx + dx - pr, eye_y - pr * 1.2,
                        cx + dx + pr, eye_y + pr * 1.2,
                        fill=colors["eye"], outline="", tags="fairy"
                    )
                    hr = eye_r * 0.25
                    self.canvas.create_oval(
                        cx + dx + pr * 0.3 - hr, eye_y - pr * 0.5 - hr,
                        cx + dx + pr * 0.3 + hr, eye_y - pr * 0.5 + hr,
                        fill="white", outline="", tags="fairy"
                    )

        # ── 嘴巴 ──
        mouth_y = cy + s * 0.15
        if self.state in (FairyState.SLEEPING, FairyState.BLIND):
            self.canvas.create_oval(
                cx - s * 0.04, mouth_y - s * 0.03,
                cx + s * 0.04, mouth_y + s * 0.03,
                fill=colors["cheek"], outline="", tags="fairy"
            )
        elif self.state == FairyState.SPEAK:
            mouth_open = s * 0.04 + math.sin(self._mouth_phase) * s * 0.03
            self.canvas.create_oval(
                cx - s * 0.08, mouth_y - mouth_open,
                cx + s * 0.08, mouth_y + mouth_open,
                fill=colors["cheek"], outline=colors["glow"], width=1, tags="fairy"
            )
        elif self.state == FairyState.HAPPY:
            self.canvas.create_arc(
                cx - s * 0.1, mouth_y - s * 0.03,
                cx + s * 0.1, mouth_y + s * 0.08,
                start=0, extent=180, style="chord",
                fill=colors["cheek"], outline=colors["glow"], width=1, tags="fairy"
            )
        elif self.state == FairyState.WARN:
            self.canvas.create_line(
                cx - s * 0.08, mouth_y,
                cx - s * 0.03, mouth_y + s * 0.05,
                cx + s * 0.03, mouth_y - s * 0.05,
                cx + s * 0.08, mouth_y,
                fill=colors["eye"], width=2, tags="fairy"
            )
        else:
            self.canvas.create_arc(
                cx - s * 0.1, mouth_y - s * 0.05,
                cx + s * 0.1, mouth_y + s * 0.08,
                start=0, extent=180, style="arc",
                outline=colors["eye"], width=1.5, tags="fairy"
            )

        # ── 腮红 ──
        cheek_r = s * 0.08
        for dx in [-s * 0.3, s * 0.3]:
            self.canvas.create_oval(
                cx + dx - cheek_r, cy + s * 0.02 - cheek_r,
                cx + dx + cheek_r, cy + s * 0.02 + cheek_r,
                fill=colors["cheek"], outline="", tags="fairy"
            )

        # ── 小星星装饰 ──
        star_r = s * 0.03
        for angle in [0, 90, 180, 270]:
            rad = math.radians(angle)
            sx = cx + math.cos(rad) * s * 0.65
            sy = cy - s * 0.1 + math.sin(rad) * s * 0.65
            pts = []
            for i in range(4):
                a = math.radians(i * 90 + 45)
                pts.extend([sx + star_r * math.cos(a), sy + star_r * math.sin(a)])
            if len(pts) == 8:
                self.canvas.create_polygon(
                    pts, fill=colors["glow"], outline="", tags="fairy"
                )

    def _should_blink(self) -> bool:
        self._blink_counter += 1
        if self._blink_counter > 80:
            self._blink_counter = 0
            return True
        return False

    def set_state(self, state: FairyState):
        if state != self.state:
            self.state = state
            self._draw()
            logger.debug(f"Ghost 状态: {state.value}")

    def _start_breath_animation(self):
        self._breath_phase += 0.03
        offset_y = math.sin(self._breath_phase) * 2
        try:
            current_y = getattr(self, '_last_offset_y', 0)
            self.canvas.move("fairy", 0, offset_y - current_y)
            self._last_offset_y = offset_y
        except Exception:
            pass
        if self.state == FairyState.SPEAK:
            self._mouth_phase += 0.3
            self._draw()
        try:
            self._animation_id = self.canvas.after(50, self._start_breath_animation)
        except Exception:
            pass

    def move_to(self, x: int, y: int):
        dx = x - self.x
        dy = y - self.y
        self.canvas.move("fairy", dx, dy)
        self.x = x
        self.y = y

    def contains(self, x: int, y: int) -> bool:
        r = self.size * 0.8
        return (x - self.x) ** 2 + (y - self.y) ** 2 <= r ** 2

    def destroy(self):
        if self._animation_id:
            try:
                self.canvas.after_cancel(self._animation_id)
            except Exception:
                pass
        self.canvas.delete("fairy")
