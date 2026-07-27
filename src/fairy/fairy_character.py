"""
NURO 2D 角色 — 猫娘桌面宠物

萌系猫娘：猫耳、大眼睛、胡须、尾巴、腮红
状态驱动颜色变化 + 呼吸动画
"""

import logging
import math
import tkinter as tk
from enum import Enum

logger = logging.getLogger(__name__)


class FairyState(Enum):
    """角色状态"""
    IDLE = "idle"           # 待机
    OBSERVING = "observing" # 观察中
    SPEAKING = "speaking"   # 说话中
    THINKING = "thinking"   # 思考中
    SLEEPING = "sleeping"   # 睡眠（眼瞎耳聋模式）


class FairyCharacter:
    """
    猫娘 2D 角色（Tkinter Canvas）

    部件：
    - 猫耳（三角，内侧粉色）
    - 圆脸 + 大眼睛（高光）
    - 小胡须（6根）
    - 腮红（椭圆粉团）
    - 嘴巴（小三角/弯月）
    - 身体（椭圆，带尾巴）
    """

    COLORS = {
        FairyState.IDLE:      {"bg": "#ffe4e6", "fg": "#f472b6", "glow": "#ec4899", "cheek": "#fda4af"},
        FairyState.OBSERVING: {"bg": "#dbeafe", "fg": "#60a5fa", "glow": "#3b82f6", "cheek": "#93c5fd"},
        FairyState.SPEAKING:  {"bg": "#d1fae5", "fg": "#34d399", "glow": "#10b981", "cheek": "#6ee7b7"},
        FairyState.THINKING:  {"bg": "#fef3c7", "fg": "#fbbf24", "glow": "#f59e0b", "cheek": "#fcd34d"},
        FairyState.SLEEPING:  {"bg": "#e5e7eb", "fg": "#9ca3af", "glow": "#6b7280", "cheek": "#d1d5db"},
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

        self._draw()
        self._start_breath_animation()

    def _draw(self):
        """绘制猫娘"""
        self.canvas.delete("fairy")
        colors = self.COLORS[self.state]
        s = self.size  # 基准尺寸

        # ── 尾巴（身体后面，先画）──
        tail_x = self.x - s * 0.7
        tail_y = self.y + s * 0.3
        self.canvas.create_line(
            tail_x, tail_y,
            tail_x - s * 0.4, tail_y - s * 0.5,
            tail_x - s * 0.2, tail_y - s * 0.8,
            fill=colors["glow"], width=max(2, s // 15),
            smooth=True, capstyle="round", tags="fairy"
        )

        # ── 身体（椭圆）──
        body_rx = s * 0.45
        body_ry = s * 0.35
        body_y = self.y + s * 0.35
        self.canvas.create_oval(
            self.x - body_rx, body_y - body_ry,
            self.x + body_rx, body_y + body_ry,
            fill=colors["bg"], outline=colors["glow"], width=2, tags="fairy"
        )

        # ── 猫耳（三角）──
        ear_size = s * 0.3
        ear_base_y = self.y - s * 0.35
        for dx in [-s * 0.35, s * 0.35]:
            # 外耳
            self.canvas.create_polygon(
                dx - ear_size * 0.6, ear_base_y + ear_size * 0.5,
                dx + ear_size * 0.6, ear_base_y + ear_size * 0.5,
                dx, ear_base_y - ear_size * 0.8,
                fill=colors["fg"], outline=colors["glow"], width=1, tags="fairy"
            )
            # 内耳（粉色）
            inner_scale = 0.5
            self.canvas.create_polygon(
                dx - ear_size * 0.6 * inner_scale, ear_base_y + ear_size * 0.5 * inner_scale + 3,
                dx + ear_size * 0.6 * inner_scale, ear_base_y + ear_size * 0.5 * inner_scale + 3,
                dx, ear_base_y - ear_size * 0.4 + 3,
                fill="#fce7f3", outline="", tags="fairy"
            )

        # ── 脸（大圆）──
        face_rx = s * 0.55
        face_ry = s * 0.5
        self.canvas.create_oval(
            self.x - face_rx, self.y - face_ry,
            self.x + face_rx, self.y + face_ry,
            fill=colors["bg"], outline=colors["glow"], width=2, tags="fairy"
        )

        # ── 腮红 ──
        cheek_r = s * 0.12
        for dx in [-s * 0.38, s * 0.38]:
            self.canvas.create_oval(
                dx - cheek_r, self.y + s * 0.05 - cheek_r // 2,
                dx + cheek_r, self.y + s * 0.05 + cheek_r // 2,
                fill=colors["cheek"], outline="", tags="fairy"
            )

        # ── 眼睛 ──
        eye_r = s * 0.14
        eye_y = self.y - s * 0.1
        for dx in [-s * 0.22, s * 0.22]:
            if self.state == FairyState.SLEEPING:
                # 闭线
                self.canvas.create_arc(
                    dx - eye_r, eye_y - eye_r // 2,
                    dx + eye_r, eye_y + eye_r // 2,
                    start=0, extent=180, style="arc",
                    outline=colors["fg"], width=2, tags="fairy"
                )
            else:
                # 大眼（外圈 + 瞳孔 + 高光）
                blink = self._should_blink()
                if blink:
                    # 眨眼：横线
                    self.canvas.create_line(
                        dx - eye_r, eye_y, dx + eye_r, eye_y,
                        fill=colors["fg"], width=2, tags="fairy"
                    )
                else:
                    # 白底
                    self.canvas.create_oval(
                        dx - eye_r, eye_y - eye_r * 1.2,
                        dx + eye_r, eye_y + eye_r * 1.2,
                        fill="white", outline=colors["fg"], width=1, tags="fairy"
                    )
                    # 瞳孔（大）
                    pr = eye_r * 0.65
                    self.canvas.create_oval(
                        dx - pr, eye_y - pr * 1.2,
                        dx + pr, eye_y + pr * 1.2,
                        fill=colors["fg"], outline="", tags="fairy"
                    )
                    # 高光（小白点）
                    hr = eye_r * 0.22
                    self.canvas.create_oval(
                        dx + pr * 0.3 - hr, eye_y - pr * 0.6 - hr,
                        dx + pr * 0.3 + hr, eye_y - pr * 0.6 + hr,
                        fill="white", outline="", tags="fairy"
                    )

        # ── 胡须 ──
        whisker_len = s * 0.4
        whisker_y = self.y + s * 0.08
        whisker_dy = s * 0.08
        for dx_sign in [-1, 1]:
            base_x = self.x + dx_sign * s * 0.25
            for dy_offset in [-whisker_dy, 0, whisker_dy]:
                self.canvas.create_line(
                    base_x, whisker_y + dy_offset,
                    base_x + dx_sign * whisker_len, whisker_y + dy_offset + (2 if dy_offset == 0 else dy_offset * 0.3),
                    fill=colors["fg"], width=max(1, s // 40), tags="fairy"
                )

        # ── 嘴巴 ──
        mouth_y = self.y + s * 0.2
        if self.state == FairyState.SLEEPING:
            # Z z z
            self.canvas.create_text(
                self.x + s * 0.5, self.y - s * 0.5,
                text="Z z z", fill=colors["fg"],
                font=("微软雅黑", max(6, s // 10)), tags="fairy"
            )
        elif self.state == FairyState.SPEAKING:
            # 张开的小圆嘴
            self.canvas.create_oval(
                self.x - s * 0.08, mouth_y - s * 0.04,
                self.x + s * 0.08, mouth_y + s * 0.1,
                fill="#ff6b6b", outline="#e11d48", width=1, tags="fairy"
            )
        else:
            # 小三角嘴（猫嘴）
            self.canvas.create_polygon(
                self.x, mouth_y - s * 0.03,
                self.x - s * 0.06, mouth_y + s * 0.04,
                self.x + s * 0.06, mouth_y + s * 0.04,
                fill="#fda4af", outline=colors["fg"], width=1, tags="fairy"
            )

    def _should_blink(self) -> bool:
        """眨眼逻辑"""
        self._blink_counter += 1
        if self._blink_counter > 120:  # ~6秒眨一次
            self._blink_counter = 0
            return True
        return False

    def set_state(self, state: FairyState):
        """切换状态"""
        if state != self.state:
            self.state = state
            self._draw()
            logger.debug(f"角色状态: {state.value}")

    def _start_breath_animation(self):
        """呼吸动画（轻微缩放 + 浮动）"""
        self._breath_phase += 0.04
        offset_y = math.sin(self._breath_phase) * 2
        try:
            self.canvas.move("fairy", 0, offset_y - getattr(self, '_last_offset_y', 0))
            self._last_offset_y = offset_y
        except Exception:
            pass
        try:
            self._animation_id = self.canvas.after(50, self._start_breath_animation)
        except Exception:
            pass

    def move_to(self, x: int, y: int):
        """移动角色"""
        dx = x - self.x
        dy = y - self.y
        self.canvas.move("fairy", dx, dy)
        self.x = x
        self.y = y

    def contains(self, x: int, y: int) -> bool:
        """点是否在角色范围内"""
        r = self.size
        return (x - self.x) ** 2 + (y - self.y) ** 2 <= r ** 2

    def destroy(self):
        """清理"""
        if self._animation_id:
            try:
                self.canvas.after_cancel(self._animation_id)
            except Exception:
                pass
        self.canvas.delete("fairy")
