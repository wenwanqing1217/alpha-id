"""
NURO Ghost — Ghost Platform 桌面精灵

角色形象：Ghost Platform 幽灵（白色幽灵 + 紫色光晕）
替代原猫娘形象，与前端 GhostSprite 保持一致。

架构：
  - ghost_character  : Tkinter Canvas 幽灵角色
  - ghost_brain      : Gateway 聊天 + Ollama 本地推理
  - ghost_voice      : 语音输入/输出（可选）
  - ghost_observer   : 屏幕活动观察
  - ghost_popup      : 气泡通知
  - ghost_memory     : 双链记忆（通过 Gateway）
  - ghost_identity   : Alpha-ID 身份

与 Ghost Platform 衔接：
  - 对话 → Gateway /v1/human/chat
  - 记忆 → Gateway /v1/human/memory/*
  - 身份 → Gateway /v1/human/identity
"""

import logging
import math
import tkinter as tk
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class GhostState(Enum):
    """幽灵状态（与 AidNuro 主类兼容）"""
    IDLE = "idle"           # 待机（漂浮）
    OBSERVING = "observing" # 观察中（眼亮）
    SPEAK = "speak"         # 说话中（嘴动）
    THINK = "think"         # 思考中（旋转/缩瞳）
    LISTEN = "listen"       # 聆听中
    HAPPY = "happy"         # 开心
    WARN = "warn"           # 警告
    BLIND = "blind"         # 眼瞎耳聋模式
    SLEEPING = "sleeping"   # 睡眠


class GhostCharacter:
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
        GhostState.IDLE:      {"body": "#ffffff", "glow": "#8b5cf6", "eye": "#1e1b4b", "cheek": "#c4b5fd"},
        GhostState.OBSERVING: {"body": "#ffffff", "glow": "#38bdf8", "eye": "#0c4a6e", "cheek": "#7dd3fc"},
        GhostState.SPEAK:     {"body": "#ffffff", "glow": "#10b981", "eye": "#064e3b", "cheek": "#6ee7b7"},
        GhostState.THINK:     {"body": "#f5f3ff", "glow": "#f59e0b", "eye": "#78350f", "cheek": "#fcd34d"},
        GhostState.LISTEN:    {"body": "#ffffff", "glow": "#3b82f6", "eye": "#1e3a5f", "cheek": "#93c5fd"},
        GhostState.HAPPY:     {"body": "#ffffff", "glow": "#10b981", "eye": "#064e3b", "cheek": "#6ee7b7"},
        GhostState.WARN:      {"body": "#fef3c7", "glow": "#ef4444", "eye": "#7f1d1d", "cheek": "#fca5a5"},
        GhostState.BLIND:     {"body": "#e5e7eb", "glow": "#6b7280", "eye": "#9ca3af", "cheek": "#d1d5db"},
        GhostState.SLEEPING:  {"body": "#e5e7eb", "glow": "#6b7280", "eye": "#9ca3af", "cheek": "#d1d5db"},
    }

    def __init__(self, canvas: tk.Canvas, x: int = 200, y: int = 200, size: int = 80):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.size = size
        self.state = GhostState.IDLE
        self._animation_id = None
        self._breath_phase = 0.0
        self._blink_counter = 0
        self._mouth_phase = 0

        self._draw()
        self._start_breath_animation()

    def _draw(self):
        """绘制 Ghost 幽灵"""
        self.canvas.delete("ghost")
        colors = self.COLORS[self.state]
        s = self.size
        cx, cy = self.x, self.y

        # ── 光晕（外层柔光）──
        glow_r = s * 0.8
        self.canvas.create_oval(
            cx - glow_r, cy - glow_r,
            cx + glow_r, cy + glow_r,
            fill="", outline=colors["glow"], width=1, tags="ghost"
        )
        # 第二层光晕
        glow_r2 = s * 1.1
        self.canvas.create_oval(
            cx - glow_r2, cy - glow_r2,
            cx + glow_r2, cy + glow_r2,
            fill="", outline=colors["glow"], width=0.5, tags="ghost"
        )

        # ── 幽灵身体（圆顶 + 波浪底边）──
        body_top = cy - s * 0.55
        body_bottom = cy + s * 0.5
        body_width = s * 0.55

        # 波浪底边的三个波峰
        wave_w = body_width * 2 / 3
        wave_h = s * 0.1
        bottom_y = body_bottom

        # 身体轮廓点
        points = [
            cx - body_width, bottom_y,          # 左下起点
            cx - body_width, cy + s * 0.1,       # 左侧
            cx - body_width * 0.7, body_top,     # 左上圆弧
            cx, body_top - s * 0.05,             # 头顶
            cx + body_width * 0.7, body_top,     # 右上圆弧
            cx + body_width, cy + s * 0.1,       # 右侧
            cx + body_width, bottom_y,           # 右下
        ]
        # 波浪底边
        wave_points = [
            cx + body_width, bottom_y,
            cx + body_width - wave_w * 0.3, bottom_y - wave_h,
            cx + body_width - wave_w * 0.6, bottom_y + wave_h * 0.5,
            cx + body_width - wave_w, bottom_y - wave_h * 0.8,
            cx + body_width - wave_w * 1.3, bottom_y + wave_h * 0.3,
            cx - body_width, bottom_y,
        ]

        # 身体填充
        body_coords = [
            cx - body_width, cy + s * 0.1,
            cx - body_width * 0.7, body_top,
            cx, body_top - s * 0.05,
            cx + body_width * 0.7, body_top,
            cx + body_width, cy + s * 0.1,
            cx + body_width, bottom_y,
            cx + body_width - wave_w * 0.3, bottom_y - wave_h,
            cx + body_width - wave_w * 0.6, bottom_y + wave_h * 0.5,
            cx + body_width - wave_w, bottom_y - wave_h * 0.8,
            cx + body_width - wave_w * 1.3, bottom_y + wave_h * 0.3,
            cx - body_width, bottom_y,
        ]
        self.canvas.create_polygon(
            body_coords,
            fill=colors["body"], outline=colors["glow"], width=2,
            tags="ghost"
        )

        # ── 眼睛 ──
        eye_r = s * 0.12
        eye_y = cy - s * 0.1
        eye_spacing = s * 0.2

        if self.state == GhostState.SLEEPING:
            # 闭眼（弧线）
            for dx in [-eye_spacing, eye_spacing]:
                self.canvas.create_arc(
                    cx + dx - eye_r, eye_y - eye_r * 0.5,
                    cx + dx + eye_r, eye_y + eye_r * 0.5,
                    start=0, extent=180, style="arc",
                    outline=colors["eye"], width=2, tags="ghost"
                )
        elif self.state == GhostState.THINKING:
            # 思考眼（螺旋状，用旋转线表示）
            for dx in [-eye_spacing, eye_spacing]:
                self.canvas.create_oval(
                    cx + dx - eye_r, eye_y - eye_r,
                    cx + dx + eye_r, eye_y + eye_r,
                    fill=colors["eye"], outline="", tags="ghost"
                )
                # 小高光
                hr = eye_r * 0.3
                self.canvas.create_oval(
                    cx + dx + eye_r * 0.2 - hr, eye_y - eye_r * 0.3 - hr,
                    cx + dx + eye_r * 0.2 + hr, eye_y - eye_r * 0.3 + hr,
                    fill="white", outline="", tags="ghost"
                )
        else:
            # 正常大眼（椭圆 + 瞳孔 + 高光）
            for dx in [-eye_spacing, eye_spacing]:
                if self._should_blink():
                    # 眨眼
                    self.canvas.create_line(
                        cx + dx - eye_r, eye_y,
                        cx + dx + eye_r, eye_y,
                        fill=colors["eye"], width=2, tags="ghost"
                    )
                else:
                    # 白底
                    self.canvas.create_oval(
                        cx + dx - eye_r, eye_y - eye_r * 1.3,
                        cx + dx + eye_r, eye_y + eye_r * 1.3,
                        fill="white", outline=colors["eye"], width=1, tags="ghost"
                    )
                    # 瞳孔
                    pr = eye_r * 0.7
                    self.canvas.create_oval(
                        cx + dx - pr, eye_y - pr * 1.2,
                        cx + dx + pr, eye_y + pr * 1.2,
                        fill=colors["eye"], outline="", tags="ghost"
                    )
                    # 高光
                    hr = eye_r * 0.25
                    self.canvas.create_oval(
                        cx + dx + pr * 0.3 - hr, eye_y - pr * 0.5 - hr,
                        cx + dx + pr * 0.3 + hr, eye_y - pr * 0.5 + hr,
                        fill="white", outline="", tags="ghost"
                    )

        # ── 嘴巴 ──
        mouth_y = cy + s * 0.15
        if self.state in (GhostState.SLEEPING, GhostState.BLIND):
            # 小圆嘴（睡觉/眼瞎）
            self.canvas.create_oval(
                cx - s * 0.04, mouth_y - s * 0.03,
                cx + s * 0.04, mouth_y + s * 0.03,
                fill=colors["cheek"], outline="", tags="ghost"
            )
        elif self.state == GhostState.SPEAK:
            # 张嘴（椭圆，带动画相位）
            mouth_open = s * 0.04 + math.sin(self._mouth_phase) * s * 0.03
            self.canvas.create_oval(
                cx - s * 0.08, mouth_y - mouth_open,
                cx + s * 0.08, mouth_y + mouth_open,
                fill=colors["cheek"], outline=colors["glow"], width=1, tags="ghost"
            )
        elif self.state == GhostState.HAPPY:
            # 大笑嘴
            self.canvas.create_arc(
                cx - s * 0.1, mouth_y - s * 0.03,
                cx + s * 0.1, mouth_y + s * 0.08,
                start=0, extent=180, style="chord",
                fill=colors["cheek"], outline=colors["glow"], width=1, tags="ghost"
            )
        elif self.state == GhostState.WARN:
            # 警告嘴（波浪）
            self.canvas.create_line(
                cx - s * 0.08, mouth_y,
                cx - s * 0.03, mouth_y + s * 0.05,
                cx + s * 0.03, mouth_y - s * 0.05,
                cx + s * 0.08, mouth_y,
                fill=colors["eye"], width=2, tags="ghost"
            )
        else:
            # 微笑（弧线）
            self.canvas.create_arc(
                cx - s * 0.1, mouth_y - s * 0.05,
                cx + s * 0.1, mouth_y + s * 0.08,
                start=0, extent=180, style="arc",
                outline=colors["eye"], width=1.5, tags="ghost"
            )

        # ── 腮红 ──
        cheek_r = s * 0.08
        for dx in [-s * 0.3, s * 0.3]:
            self.canvas.create_oval(
                cx + dx - cheek_r, cy + s * 0.02 - cheek_r,
                cx + dx + cheek_r, cy + s * 0.02 + cheek_r,
                fill=colors["cheek"], outline="", tags="ghost"
            )

        # ── 小星星装饰（头部周围）──
        star_r = s * 0.03
        for angle in [0, 90, 180, 270]:
            rad = math.radians(angle)
            sx = cx + math.cos(rad) * s * 0.65
            sy = cy - s * 0.1 + math.sin(rad) * s * 0.65
            self._draw_star(sx, sy, star_r, colors["glow"])

    def _draw_star(self, x, y, r, color):
        """绘制小四角星"""
        pts = []
        for i in range(4):
            angle = math.radians(i * 90 + 45)
            pts.extend([x + r * math.cos(angle), y + r * math.sin(angle)])
        if len(pts) == 8:
            self.canvas.create_polygon(
                pts, fill=color, outline="", tags="ghost"
            )

    def _should_blink(self) -> bool:
        """眨眼逻辑（约每 4 秒眨一次）"""
        self._blink_counter += 1
        if self._blink_counter > 80:
            self._blink_counter = 0
            return True
        return False

    def set_state(self, state: GhostState):
        """切换状态"""
        if state != self.state:
            self.state = state
            self._draw()
            logger.debug(f"Ghost 状态: {state.value}")

    def _start_breath_animation(self):
        """呼吸浮动动画"""
        self._breath_phase += 0.03
        offset_y = math.sin(self._breath_phase) * 2
        try:
            current_y = getattr(self, '_last_offset_y', 0)
            self.canvas.move("ghost", 0, offset_y - current_y)
            self._last_offset_y = offset_y
        except Exception:
            pass

        # 说话时嘴巴动画
        if self.state == GhostState.SPEAK:
            self._mouth_phase += 0.3
            self._draw()

        try:
            self._animation_id = self.canvas.after(50, self._start_breath_animation)
        except Exception:
            pass

    def move_to(self, x: int, y: int):
        """移动角色"""
        dx = x - self.x
        dy = y - self.y
        self.canvas.move("ghost", dx, dy)
        self.x = x
        self.y = y

    def contains(self, x: int, y: int) -> bool:
        """点是否在角色范围内"""
        r = self.size * 0.8
        return (x - self.x) ** 2 + (y - self.y) ** 2 <= r ** 2

    def destroy(self):
        """清理"""
        if self._animation_id:
            try:
                self.canvas.after_cancel(self._animation_id)
            except Exception:
                pass
        self.canvas.delete("ghost")
