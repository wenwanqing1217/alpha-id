"""
AID Daemon v2 — 桌面精灵
暗色磨砂玻璃悬浮球 + 持续对话面板 + 语音唤醒 + 边语音边打字
"""

import argparse
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 版本 ──
try:
    from alpha_id import __version__

    VERSION = __version__
except ImportError:
    VERSION = "0.2.0"

# ── DWM 亚克力效果 ──
HAS_DWM_ACRYLIC = False
try:
    import ctypes
    from ctypes import wintypes

    HAS_DWM_ACRYLIC = True
except Exception:
    pass

# ── LLM 大脑 ──
HAS_LLM = False
HAS_MEMORY = False
try:
    from core.memory_store import MemoryStore
    from core.storage_sqlite import SqliteStorage
    from fairy_agent import FairyBrain

    HAS_LLM = bool(os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", ""))
    HAS_MEMORY = True
except ImportError:
    pass

# ── 画像 ──
try:
    from alpha_id.profile_schema import load_profile, profile_exists
    from alpha_id.profile_schema import summary as profile_summary

    HAS_PROFILE = True
except ImportError:
    HAS_PROFILE = False

# ── 工具（延迟加载） ──
HAS_SCREEN = False
HAS_OCR = False
HAS_WINDOW = False
_cap_err = {}
try:
    from tools.screen_capture import capture_full_screen

    HAS_SCREEN = True
except ImportError as e:
    _cap_err["截图"] = str(e)
try:
    from tools.ocr import extract_text as ocr_text

    HAS_OCR = True
except ImportError as e:
    _cap_err["OCR"] = str(e)
try:
    from tools.window_control import (
        get_mouse_position,
        list_application_windows,
    )

    HAS_WINDOW = True
except ImportError as e:
    _cap_err["窗口控制"] = str(e)

# ── TTS ──
HAS_TTS = False
_tts_engine = None
try:
    import win32com.client

    _tts_engine = win32com.client.Dispatch("SAPI.SpVoice")
    voices = _tts_engine.GetVoices()
    for i in range(voices.Count):
        if "Chinese" in str(voices.Item(i).GetDescription()) or "中文" in str(voices.Item(i).GetDescription()):
            _tts_engine.Voice = voices.Item(i)
            break
    HAS_TTS = True
except Exception:
    pass

# ── STT ──
HAS_SPEECH = False
HAS_SPEECH_RECOGNITION = False  # 别名，兼容测试
try:
    import speech_recognition  # noqa: F401

    HAS_SPEECH = True
    HAS_SPEECH_RECOGNITION = True
except ImportError:
    pass

# ── Tkinter ──
try:
    import tkinter as tk
except ImportError:
    sys.exit("tkinter 不可用。请安装 Python 时勾选 'tcl/tk and IDLE'。")


# ══════════════════════════════════════════════════════════
#  DWM 亚克力效果（Win10 1803+ / Win11）
# ══════════════════════════════════════════════════════════


def apply_acrylic(hwnd: int, tint_color: int = 0x1A1A2E, alpha: int = 180):
    """
    为窗口启用 Windows 10/11 亚克力模糊效果。
    tint_color: 0xAABBGGRR (alpha, blue, green, red)
    alpha: 0-255 透明度
    """
    if not HAS_DWM_ACRYLIC:
        return False
    try:

        class AccentPolicy(ctypes.Structure):
            _fields_ = [
                ("AccentState", wintypes.DWORD),
                ("AccentFlags", wintypes.DWORD),
                ("GradientColor", wintypes.DWORD),
                ("AnimationId", wintypes.DWORD),
            ]

        class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", wintypes.DWORD),
                ("Data", ctypes.POINTER(AccentPolicy)),
                ("SizeOfData", ctypes.c_size_t),
            ]

        # 构建带 alpha 的色调颜色
        gradient = (min(255, alpha) << 24) | (tint_color & 0xFFFFFF)

        accent = AccentPolicy()
        accent.AccentState = 4  # ACCENT_ENABLE_ACRYLIC
        accent.GradientColor = gradient
        accent.AccentFlags = 0

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.SizeOfData = ctypes.sizeof(accent)
        data.Data = ctypes.pointer(accent)

        ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════
#  调色板
# ══════════════════════════════════════════════════════════


class Palette:
    BG_DARK = "#0F0F1A"
    BG_FROST = "#1A1A2E"
    BG_LIGHT = "#252540"
    BG_CARD = "#1E1E35"
    ACCENT = "#7C6FFF"
    ACCENT_DIM = "#5A4FBF"
    ACCENT_GLOW = "#9D8FFF"
    TEXT_PRIMARY = "#EEEEFF"
    TEXT_SECONDARY = "#8888BB"
    TEXT_DIM = "#555577"
    BORDER = "#2A2A4E"
    SUCCESS = "#44DDBB"
    WARN = "#FFB347"
    USER_BUBBLE = "#3A2D8A"
    AI_BUBBLE = "#1E1E38"
    INPUT_BG = "#16162A"


# ══════════════════════════════════════════════════════════
#  AID 桌面精灵 v2
# ══════════════════════════════════════════════════════════


class AIDFairy:
    """AID 桌面精灵 — 亚克力小岛 + 持续对话面板 + 语音唤醒"""

    ISLAND_W = 140
    ISLAND_H = 44
    ISLAND_R = 22  # 圆角半径（全圆角 = 高度/2）
    PANEL_W = 400
    PANEL_H = 560
    WAKE_WORDS = ["你好aid", "你好 aid", "嘿aid", "嘿 aid", "hey aid", "aid"]

    def __init__(self, no_mcp=False, no_brain=False, debug=False):
        self._debug = debug
        self._no_brain = no_brain
        self._no_mcp = no_mcp

        # ── 球窗口 ──
        self.ball = tk.Tk()
        self.ball.title("AID")
        self.ball.overrideredirect(True)
        self.ball.attributes("-topmost", True)
        self.ball.configure(bg="#0F0F1A")
        self.ball.wm_attributes("-alpha", 0.92)

        self._center_ball()
        self._ball_hwnd = None
        self._apply_ball_acrylic()

        # ── 状态 ──
        self._drag_data = {"x": 0, "y": 0, "dragging": False}
        self._chat_visible = False

        # ── 唤醒词（支持环境变量覆盖） ──
        env_wake = os.getenv("AID_WAKE_WORDS", "")
        if env_wake:
            self.WAKE_WORDS = [w.strip().lower() for w in env_wake.split(",") if w.strip()]

        # ── MCP ──
        self._mcp_process: Optional[subprocess.Popen] = None

        # ── LLM 大脑 ──
        self._brain: Optional["FairyBrain"] = None
        self._memory_store: Optional["MemoryStore"] = None
        self._init_brain()

        # ── 会话历史（UI 级） ──
        self._messages: list = []

        # ── 引用 ──
        self._chat_win: Optional[tk.Toplevel] = None
        self._result_win: Optional[tk.Toplevel] = None

        # ── 呼吸动画 ──
        self._breath_dir = 1
        self._breath_val = 0.92

        # ── 绘制球 ──
        self._create_ball()

        # ── 右键菜单 ──
        self._create_menu()

        # ── 语音唤醒 ──
        if HAS_SPEECH:
            self._start_wakeup_listener()

        # ── 呼吸动画启动 ──
        self._animate_breath()

        # ── MCP ──
        if not no_mcp:
            self._start_mcp_server()

    # ── 窗口布局 ──

    def _center_ball(self):
        s = self.ISLAND_W
        sw = self.ball.winfo_screenwidth()
        x = sw - s - 30
        y = 60
        self.ball.geometry(f"{self.ISLAND_W}x{self.ISLAND_H}+{x}+{y}")

    def _apply_ball_acrylic(self):
        try:
            self.ball.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.ball.winfo_id())
            self._ball_hwnd = hwnd
            apply_acrylic(hwnd, tint_color=0x0F0F1A, alpha=160)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════
    #  小岛 v2 — Dynamic Island × Win11 亚克力
    # ═══════════════════════════════════════════════════════

    def _create_pill_rect(self, canvas, x1, y1, x2, y2, r, **kwargs):
        """绘制圆角矩形（药丸形）"""
        points = [
            x1 + r,
            y1,
            x2 - r,
            y1,
            x2,
            y1,
            x2,
            y1 + r,
            x2,
            y2 - r,
            x2,
            y2,
            x2 - r,
            y2,
            x1 + r,
            y2,
            x1,
            y2,
            x1,
            y2 - r,
            x1,
            y1 + r,
            x1,
            y1,
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    def _create_ball(self):
        """绘制小岛——Dynamic Island 风格，Win11 亚克力"""
        w, h, r = self.ISLAND_W, self.ISLAND_H, self.ISLAND_R
        c = tk.Canvas(self.ball, width=w, height=h, bg=Palette.BG_DARK, highlightthickness=0)
        c.pack()
        m = 2

        # ── 外发光层（呼吸光） ──
        self._glow = self._create_pill_rect(
            c,
            m - 1,
            m - 1,
            w - m + 1,
            h - m + 1,
            r + 1,
            fill="",
            outline=Palette.ACCENT_DIM,
            width=2,
        )

        # ── 主体：磨砂玻璃 ──
        self._pill = self._create_pill_rect(
            c,
            m,
            m,
            w - m,
            h - m,
            r,
            fill=Palette.BG_FROST,
            outline=Palette.BORDER,
            width=1,
        )

        # ── 内发光（左上高光弧） ──
        c.create_arc(
            m + 6, m + 4, w - m - 6, h - m + 8, start=-30, extent=160, fill="", outline="white", width=1.2, style="arc"
        )

        # ── 底部反光 ──
        c.create_arc(
            m + 12,
            m - 4,
            w - m - 12,
            h - m + 20,
            start=150,
            extent=100,
            fill="",
            outline=Palette.TEXT_SECONDARY,
            width=0.8,
            style="arc",
        )

        # ── 左侧：状态指示点 ──
        self._dot = c.create_oval(14, h // 2 - 4, 14 + 8, h // 2 + 4, fill=Palette.SUCCESS, outline="")

        # ── 中间：AID 文字 ──
        c.create_text(
            w // 2 - 2, h // 2, text="AID", fill=Palette.ACCENT_GLOW, font=("Segoe UI", 13, "bold"), anchor="center"
        )

        # ── 右侧：状态指示环（脉动） ──
        self._ring = c.create_oval(
            w - 24, h // 2 - 5, w - 14, h // 2 + 5, fill="", outline=Palette.ACCENT_GLOW, width=1.5
        )

        self._canvas = c

        # 交互
        c.tag_bind("all", "<Button-1>", self._on_click)
        c.tag_bind("all", "<B1-Motion>", self._on_drag)
        c.tag_bind("all", "<ButtonRelease-1>", self._on_release)
        c.tag_bind("all", "<Button-3>", self._show_menu)
        c.tag_bind("all", "<Enter>", lambda e: self._on_island_hover(True))
        c.tag_bind("all", "<Leave>", lambda e: self._on_island_hover(False))

    def _on_island_hover(self, entering: bool):
        """悬停：增强发光"""
        if entering:
            self.ball.wm_attributes("-alpha", 1.0)
            self._canvas.itemconfig(self._glow, outline=Palette.ACCENT_GLOW, width=2.5)
        else:
            self.ball.wm_attributes("-alpha", 0.92)
            self._canvas.itemconfig(self._glow, outline=Palette.ACCENT_DIM, width=2)

    def _animate_breath(self):
        """呼吸动画：状态点 + 外环脉动"""
        try:
            if not self.ball.winfo_exists():
                return
            self._breath_val += 0.04 * self._breath_dir
            if self._breath_val > 1.0:
                self._breath_val = 1.0
                self._breath_dir = -1
            elif self._breath_val < 0.3:
                self._breath_val = 0.3
                self._breath_dir = 1

            # 发光层透明度和颜色
            alpha_hex = f"{int(self._breath_val * 160):02x}"
            glow_color = Palette.ACCENT_GLOW + alpha_hex
            self._canvas.itemconfig(
                self._glow, outline=glow_color if self._breath_val > 0.5 else Palette.ACCENT_DIM + alpha_hex
            )

            # 状态点亮度
            dot_br = int(100 + 155 * self._breath_val)
            dot_color = f"#{dot_br:02x}{dot_br:02x}ff"
            self._canvas.itemconfig(self._dot, fill=dot_color)

            # 右侧环呼吸
            ring_size = 4 + int(2 * self._breath_val)
            cx, cy = self.ISLAND_W - 19, self.ISLAND_H // 2
            self._canvas.coords(self._ring, cx - ring_size, cy - ring_size, cx + ring_size, cy + ring_size)
            ring_alpha = int(150 + 105 * self._breath_val)
            self._canvas.itemconfig(self._ring, outline=f"#{ring_alpha:02x}{ring_alpha:02x}ff")

            self.ball.after(50, self._animate_breath)
        except Exception:
            pass

    # ── 交互 ──

    def _on_click(self, event):
        """单击 = 打开/聚焦聊天面板"""
        self._drag_data["x"] = event.x_root - self.ball.winfo_x()
        self._drag_data["y"] = event.y_root - self.ball.winfo_y()
        self._drag_data["dragging"] = False
        self._drag_data["click_time"] = time.time()

    def _on_drag(self, event):
        dx = abs(event.x_root - self.ball.winfo_x() - self._drag_data["x"])
        dy = abs(event.y_root - self.ball.winfo_y() - self._drag_data["y"])
        if dx > 5 or dy > 5:
            self._drag_data["dragging"] = True
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.ball.geometry(f"+{x}+{y}")

    def _on_release(self, event):
        """松开：如果是单击（非拖拽），打开聊天"""
        if not self._drag_data["dragging"]:
            self._toggle_chat()

    # ── 右键菜单 ──

    def _create_menu(self):
        self._menu = tk.Menu(
            self.ball,
            tearoff=0,
            bg=Palette.BG_DARK,
            fg=Palette.TEXT_PRIMARY,
            activebackground=Palette.ACCENT,
            activeforeground="white",
            font=("Microsoft YaHei", 10),
        )
        self._menu.add_command(label="💬 打开对话", command=self._toggle_chat)
        self._menu.add_command(label="📸 看屏幕", command=lambda: self._quick_action("看屏幕"))
        self._menu.add_command(label="🧑 我的画像", command=self._show_profile)
        if HAS_SPEECH:
            self._menu.add_command(label="🎤 语音输入", command=self._menu_voice_input)
        self._menu.add_separator()
        self._menu.add_command(label="ℹ️ 关于 AID", command=self._show_about)
        self._menu.add_separator()
        self._menu.add_command(label="退出", command=self._quit)

    def _show_menu(self, event):
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    # ═══════════════════════════════════════════════════════
    #  持续对话面板（新）
    # ═══════════════════════════════════════════════════════

    def _toggle_chat(self):
        if self._chat_win and self._chat_win.winfo_exists():
            self._chat_win.lift()
            self._chat_win.focus_set()
            self._chat_visible = True
        else:
            self._create_chat_panel()

    def _create_chat_panel(self):
        """创建持续对话面板"""
        win = tk.Toplevel(self.ball)
        win.title("AID 对话")
        win.configure(bg=Palette.BG_DARK)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.transient(self.ball)

        # 位置：小岛下方
        bx = self.ball.winfo_x()
        by = self.ball.winfo_y()
        px = bx - self.PANEL_W // 2 + self.ISLAND_W // 2
        py = by + self.ISLAND_H + 6
        # 确保不超出屏幕左边界
        if px < 10:
            px = bx + self.ISLAND_W + 6
        win.geometry(f"{self.PANEL_W}x{self.PANEL_H}+{px}+{py}")

        # 亚克力效果
        try:
            win.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            apply_acrylic(hwnd, tint_color=0x0F0F1A, alpha=200)
        except Exception:
            pass

        # ── 标题栏 ──
        title_bar = tk.Frame(win, bg=Palette.BG_DARK, height=36)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        tk.Label(
            title_bar, text="  AID", bg=Palette.BG_DARK, fg=Palette.ACCENT_GLOW, font=("Segoe UI", 11, "bold")
        ).pack(side="left")

        # 按钮组
        btn_frame = tk.Frame(title_bar, bg=Palette.BG_DARK)
        btn_frame.pack(side="right", padx=6)

        btn_style = dict(
            bg=Palette.BG_DARK,
            fg=Palette.TEXT_SECONDARY,
            bd=0,
            font=("Segoe UI", 10),
            padx=4,
            activebackground=Palette.BG_LIGHT,
            activeforeground=Palette.TEXT_PRIMARY,
            cursor="hand2",
        )

        tk.Button(btn_frame, text="🗕", **btn_style, command=lambda: win.withdraw()).pack(side="left")
        tk.Button(btn_frame, text="✕", **btn_style, command=self._close_chat).pack(side="left")

        # 标题栏拖拽
        def _sm(e):
            win._dx, win._dy = e.x_root - win.winfo_x(), e.y_root - win.winfo_y()

        def _dm(e):
            win.geometry(f"+{e.x_root - win._dx}+{e.y_root - win._dy}")

        title_bar.bind("<Button-1>", _sm)
        title_bar.bind("<B1-Motion>", _dm)

        # ── 聊天区域 ──
        chat_frame = tk.Frame(win, bg=Palette.BG_DARK)
        chat_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        chat_bg = Palette.BG_CARD
        self._chat_text = tk.Text(
            chat_frame,
            wrap="word",
            font=("Microsoft YaHei", 10),
            bg=chat_bg,
            fg=Palette.TEXT_PRIMARY,
            bd=0,
            relief="flat",
            padx=10,
            pady=8,
            spacing1=2,
            spacing3=4,
            state="disabled",
            cursor="arrow",
            highlightthickness=0,
        )
        self._chat_text.pack(side="left", fill="both", expand=True)

        # 配置标签样式
        self._chat_text.tag_config(
            "user", foreground=Palette.ACCENT_GLOW, font=("Microsoft YaHei", 9, "bold"), spacing1=4, lmargin1=40
        )
        self._chat_text.tag_config(
            "ai", foreground=Palette.TEXT_PRIMARY, font=("Microsoft YaHei", 10), spacing1=4, lmargin2=10
        )
        self._chat_text.tag_config(
            "ai_name", foreground=Palette.ACCENT, font=("Microsoft YaHei", 9, "bold"), spacing1=4
        )
        self._chat_text.tag_config("sep", foreground=Palette.BORDER, spacing1=2)
        self._chat_text.tag_config("thinking", foreground=Palette.TEXT_DIM, font=("Microsoft YaHei", 9), spacing1=2)

        # 滚动条
        scrollbar = tk.Scrollbar(
            chat_frame,
            command=self._chat_text.yview,
            bg=Palette.BG_DARK,
            troughcolor=Palette.BG_DARK,
            activebackground=Palette.ACCENT,
            width=6,
        )
        scrollbar.pack(side="right", fill="y")
        self._chat_text.configure(yscrollcommand=scrollbar.set)

        # ── 快捷操作行 ──
        quick_frame = tk.Frame(win, bg=Palette.BG_DARK)
        quick_frame.pack(fill="x", padx=8, pady=(0, 4))

        q_style = dict(
            bg=Palette.BG_LIGHT,
            fg=Palette.TEXT_SECONDARY,
            bd=0,
            font=("Microsoft YaHei", 8),
            padx=8,
            pady=2,
            cursor="hand2",
            activebackground=Palette.ACCENT_DIM,
            activeforeground="white",
        )
        tk.Button(
            quick_frame, text="📸 看屏幕", **q_style, command=lambda: self._quick_action("看看屏幕上有什么")
        ).pack(side="left", padx=2)
        tk.Button(quick_frame, text="📋 窗口", **q_style, command=lambda: self._quick_action("有哪些窗口打开了")).pack(
            side="left", padx=2
        )
        tk.Button(quick_frame, text="📍 鼠标", **q_style, command=lambda: self._quick_action("鼠标位置在哪")).pack(
            side="left", padx=2
        )
        tk.Button(quick_frame, text="🧹 清屏", **q_style, command=self._clear_chat).pack(side="right", padx=2)

        # ── 输入区域 ──
        input_frame = tk.Frame(win, bg=Palette.BG_DARK)
        input_frame.pack(fill="x", padx=8, pady=(0, 8))

        entry_bg = Palette.INPUT_BG
        entry_frame = tk.Frame(
            input_frame,
            bg=Palette.BORDER,
            bd=0,
            highlightthickness=1,
            highlightcolor=Palette.ACCENT,
            highlightbackground=Palette.BORDER,
        )
        entry_frame.pack(side="left", fill="x", expand=True)

        self._entry = tk.Entry(
            entry_frame,
            font=("Microsoft YaHei", 11),
            bd=0,
            relief="flat",
            bg=entry_bg,
            fg=Palette.TEXT_PRIMARY,
            insertbackground=Palette.TEXT_PRIMARY,
        )
        self._entry.pack(fill="x", padx=10, pady=8, ipady=2)
        self._entry.focus_set()

        def _on_enter(e):
            cmd = self._entry.get().strip()
            if cmd:
                self._entry.delete(0, "end")
                self._chat_send(cmd)

        self._entry.bind("<Return>", _on_enter)

        # 发送按钮
        tk.Button(
            input_frame,
            text="➤",
            bg=Palette.ACCENT,
            fg="white",
            bd=0,
            padx=10,
            pady=6,
            font=("Segoe UI", 12),
            cursor="hand2",
            activebackground=Palette.ACCENT_DIM,
            command=lambda: _on_enter(None),
        ).pack(side="right", padx=(6, 0))

        # 语音按钮
        if HAS_SPEECH:
            self._mic_btn = tk.Button(
                input_frame,
                text="🎤",
                bg=Palette.BG_LIGHT,
                fg=Palette.TEXT_PRIMARY,
                bd=0,
                padx=10,
                pady=6,
                font=("Segoe UI", 12),
                cursor="hand2",
                activebackground=Palette.ACCENT_DIM,
                command=self._chat_voice_input,
            )
            self._mic_btn.pack(side="right", padx=(0, 6))

        # 关闭回调
        def _on_close():
            self._chat_win = None
            self._chat_visible = False
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)

        self._chat_win = win
        self._chat_visible = True

        # 系统问候
        if not self._messages:
            self._add_chat_message(
                "ai",
                "你好，我是 **AID** — 你的桌面智能助手。\n\n"
                "💬 打字或点击 🎤 语音跟我说话\n"
                "📸 试试点「看屏幕」让我帮你看看桌面\n"
                "或者直接叫我 「你好 AID」 唤醒我",
            )

    def _add_chat_message(self, role: str, content: str):
        """添加一条消息到聊天"""
        if not self._chat_win or not self._chat_win.winfo_exists():
            return

        self._chat_text.configure(state="normal")

        if role == "user":
            self._chat_text.insert("end", "你\n", "user")
            self._chat_text.insert("end", f"{content}\n", "sep")
        elif role == "ai":
            self._chat_text.insert("end", "AID\n", "ai_name")
            # 支持简单 markdown **bold**
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", content)
            self._chat_text.insert("end", f"{clean}\n", "ai")
        elif role == "thinking":
            self._chat_text.insert("end", f"{content}\n", "thinking")
        elif role == "error":
            self._chat_text.insert("end", f"{content}\n", "thinking")

        self._chat_text.insert("end", "\n")
        self._chat_text.configure(state="disabled")
        self._chat_text.see("end")

        # 记录
        self._messages.append({"role": role, "content": content})

    def _clear_chat(self):
        """清空聊天记录"""
        if not self._chat_win or not self._chat_win.winfo_exists():
            return
        self._chat_text.configure(state="normal")
        self._chat_text.delete("1.0", "end")
        self._chat_text.configure(state="disabled")
        self._messages = []
        self._add_chat_message("ai", "已清空，重新开始～")

    def _close_chat(self):
        if self._chat_win:
            try:
                self._chat_win.destroy()
            except Exception:
                pass
        self._chat_win = None
        self._chat_visible = False

    # ── 聊天发送 ──

    def _chat_send(self, text: str):
        """发送消息到大脑"""
        if not text.strip():
            return
        self._add_chat_message("user", text)
        self._process_command(text)

    def _quick_action(self, text: str):
        """快捷按钮触发"""
        self._ensure_chat_open()
        # 模拟输入
        if self._entry:
            self._entry.delete(0, "end")
            self._entry.insert(0, text)
            self._chat_send(text)

    def _ensure_chat_open(self):
        if not self._chat_win or not self._chat_win.winfo_exists():
            self._create_chat_panel()

    # ── 语音输入（一次性的） ──

    def _chat_voice_input(self):
        """点击麦克风按钮：语音识别 → 填入输入框（可编辑后再发）"""
        if not HAS_SPEECH:
            return
        self._add_chat_message("thinking", "🎤 聆听中...")
        self._mic_btn.configure(text="🔴", state="disabled")

        def _do():
            try:
                import speech_recognition as sr

                r = sr.Recognizer()
                with sr.Microphone() as source:
                    r.adjust_for_ambient_noise(source, duration=0.3)
                    audio = r.listen(source, timeout=5, phrase_time_limit=8)
                text = r.recognize_google(audio, language="zh-CN")
                # 回填到输入框（用户可以编辑）
                self._safe_call(lambda: self._entry.delete(0, "end"))
                self._safe_call(lambda: self._entry.insert(0, text))
                self._safe_call(lambda: self._entry.focus_set())
                self._safe_call(lambda: self._remove_last_thinking())
                # 自动发送
                self._safe_call(lambda: self._chat_send(text))
            except Exception as e:
                err = (
                    f"🎤 没听清：{e}"
                    if "UnknownValueError" in str(e) or "WaitTimeoutError" in str(e)
                    else f"🎤 语音出错：{e}"
                )
                self._safe_call(lambda: self._remove_last_thinking())
                self._safe_call(lambda: self._add_chat_message("error", err))
            finally:
                self._safe_call(lambda: self._mic_btn.configure(text="🎤", state="normal"))

        threading.Thread(target=_do, daemon=True).start()

    def _menu_voice_input(self):
        """右键菜单语音输入 → 打开聊天面板后触发"""
        self._ensure_chat_open()
        self._chat_voice_input()

    def _show_profile(self):
        """打开画像窗口"""
        win = tk.Toplevel(self.ball)
        win.title("我的数字画像")
        win.configure(bg=Palette.BG_DARK)
        win.geometry("480x360")
        win.transient(self.ball)
        win.resizable(False, False)

        text_widget = tk.Text(
            win,
            wrap="word",
            bg=Palette.BG_DARK,
            fg=Palette.TEXT_PRIMARY,
            font=("Microsoft YaHei", 10),
            bd=0,
            padx=16,
            pady=12,
        )
        text_widget.pack(fill="both", expand=True)

        try:
            if HAS_PROFILE and profile_exists():
                data = load_profile()
                text = profile_summary(data)
                text_widget.insert("1.0", text)
            else:
                text_widget.insert("1.0", "还没有画像数据，请先运行 aid init 和 aid collect 采集你的数字痕迹")
        except Exception:
            text_widget.insert("1.0", "还没有画像数据，请先运行 aid init 和 aid collect 采集你的数字痕迹")

        text_widget.configure(state="disabled")

        btn_frame = tk.Frame(win, bg=Palette.BG_DARK)
        btn_frame.pack(fill="x", pady=(0, 10))
        tk.Button(
            btn_frame,
            text="关闭",
            bg=Palette.ACCENT,
            fg="white",
            bd=0,
            padx=20,
            pady=4,
            font=("Microsoft YaHei", 10),
            cursor="hand2",
            activebackground=Palette.ACCENT_DIM,
            command=win.destroy,
        ).pack()

    def _remove_last_thinking(self):
        """移除最后的"正在思考"提示"""
        if not self._chat_win or not self._chat_win.winfo_exists():
            return
        if self._messages and self._messages[-1]["role"] == "thinking":
            self._messages.pop()
            self._chat_text.configure(state="normal")
            # 删除最后两行
            try:
                last_line = int(self._chat_text.index("end-1c").split(".")[0])
                self._chat_text.delete(f"{last_line - 1}.0", "end-1c")
                self._chat_text.delete(f"{last_line - 2}.0", "end-1c")
            except Exception:
                pass
            self._chat_text.configure(state="disabled")

    def _safe_call(self, fn):
        """安全地在主线程执行 tkinter 操作"""
        try:
            self.ball.after(0, fn)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════
    #  语音唤醒
    # ═══════════════════════════════════════════════════════

    def _start_wakeup_listener(self):
        """后台监听唤醒词「你好 AID」"""

        def _listen():
            if not HAS_SPEECH:
                return
            try:
                import speech_recognition as sr

                r = sr.Recognizer()
                # 降低灵敏度以适应远场
                r.energy_threshold = 3000
                r.dynamic_energy_threshold = True
                r.pause_threshold = 0.8

                while True:
                    try:
                        with sr.Microphone() as source:
                            r.adjust_for_ambient_noise(source, duration=0.5)
                            audio = r.listen(source, timeout=2, phrase_time_limit=3)
                        text = r.recognize_google(audio, language="zh-CN")
                        text_lower = text.lower().replace(" ", "")
                        for w in self.WAKE_WORDS:
                            if w.replace(" ", "") in text_lower or text_lower in w.replace(" ", ""):
                                # 检测到唤醒词！
                                self._safe_call(self._on_wakeup)
                                break
                    except sr.WaitTimeoutError:
                        time.sleep(0.3)
                        continue
                    except sr.UnknownValueError:
                        time.sleep(0.1)
                        continue
                    except OSError:
                        time.sleep(3)
                        continue
                    except Exception:
                        if self._debug:
                            traceback.print_exc()
                        time.sleep(1)
                        continue
            except Exception:
                pass

        t = threading.Thread(target=_listen, daemon=True, name="wakeup-listener")
        t.start()

    def _on_wakeup(self):
        """唤醒：打开聊天面板 + 回应"""
        self._ensure_chat_open()
        self._add_chat_message("thinking", "👋 我在呢！")
        # 语音回话
        if HAS_TTS:

            def _say():
                try:
                    _tts_engine.Speak("在呢，有什么需要帮忙的？")
                except Exception:
                    if self._debug:
                        traceback.print_exc()

            threading.Thread(target=_say, daemon=True).start()
        self._add_chat_message("ai", "在呢～有什么需要帮忙的？")

    # ═══════════════════════════════════════════════════════
    #  LLM 大脑
    # ═══════════════════════════════════════════════════════

    def _init_brain(self):
        if self._no_brain:
            return
        if not HAS_MEMORY:
            return
        try:
            db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "fairy_memory.db")
            storage = SqliteStorage(db_path)
            self._memory_store = MemoryStore(alpha_id="desktop_fairy", storage=storage)
        except Exception as e:
            _safe_print(f"  [AID] Memory init: {e}")
            if self._debug:
                traceback.print_exc()
            self._memory_store = None

        # 检测可用的 LLM 后端（优先 API Key → 本地 Ollama）
        llm_available = HAS_LLM
        ollama_detected = False

        if not llm_available:
            try:
                import json
                import urllib.request

                req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    data = json.loads(resp.read().decode())
                    models = [m["name"] for m in data.get("models", [])]
                    if models:
                        ollama_detected = True
                        _safe_print(f"  Ollama:  ✅ 已连接（{', '.join(models[:3])}）")
            except Exception:
                pass

        try:
            if HAS_LLM or ollama_detected:
                if ollama_detected:
                    os.environ.setdefault("OPENAI_API_KEY", "ollama")
                    os.environ.setdefault("OPENAI_API_BASE", "http://localhost:11434/v1")
                    os.environ.setdefault("AID_LLM_MODEL", "llama3.2")
                self._brain = FairyBrain(fairy=self, memory_store=self._memory_store)
                if self._brain.available:
                    _safe_print(f"  Brain:  ✅ {self._brain.model}")
                else:
                    _safe_print("  Brain:  ⏳ 已加载但不可用")
                    self._brain = None
            else:
                _safe_print("  Brain:  ⏳ 未配置（设 DEEPSEEK_API_KEY 或安装 Ollama）")
        except Exception as e:
            _safe_print(f"  [AID] Brain init: {e}")
            if self._debug:
                traceback.print_exc()
            self._brain = None

    def _process_command(self, cmd: str):
        cmd = cmd.strip()
        if not cmd:
            return

        # LLM 大脑
        if self._brain and self._brain.available:
            self._add_chat_message("thinking", "💭 正在思考...")
            threading.Thread(target=self._brain_process, args=(cmd,), daemon=True).start()
            return

        # 降级（极简）
        cmd_lower = cmd.lower()
        if any(kw in cmd_lower for kw in ["看屏幕", "截图", "看看", "screenshot"]):
            self._quick_look_result()
        elif any(kw in cmd_lower for kw in ["窗口", "列表", "windows"]):
            self._list_windows_result()
        elif any(kw in cmd_lower for kw in ["鼠标", "mouse", "位置"]):
            self._mouse_position_result()
        else:
            self._add_chat_message("error", "还没有配置 AI 大脑～\n请在环境变量设置 DEEPSEEK_API_KEY")

    def _brain_process(self, cmd: str):
        """在线程中调用大脑"""
        try:
            reply = self._brain._call_llm(cmd)
            self._safe_call(lambda: self._remove_last_thinking())
            self._safe_call(lambda: self._add_chat_message("ai", reply))
            self._brain._remember(cmd, reply)
        except Exception as e:
            self._safe_call(lambda: self._remove_last_thinking())
            self._safe_call(lambda e=e: self._add_chat_message("error", f"🤖 出错了：{e}"))

    # ── 降级工具 ──

    def _quick_look_result(self):
        if not HAS_SCREEN:
            self._add_chat_message("error", "截图工具未安装")
            return
        self._add_chat_message("thinking", "📸 正在看屏幕...")

        def _do():
            try:
                img_path = capture_full_screen()
                if not img_path or not os.path.exists(img_path):
                    self._safe_call(lambda: self._add_chat_message("error", "截图失败"))
                    return
                if HAS_OCR:
                    text = ocr_text(img_path, lang="chi_sim+eng")
                    if text and text.strip():
                        preview = text[:800]
                        self._safe_call(lambda: self._remove_last_thinking())
                        self._safe_call(lambda: self._add_chat_message("ai", f"📸 屏幕上看到：\n{preview}"))
                    else:
                        self._safe_call(lambda: self._remove_last_thinking())
                        self._safe_call(lambda: self._add_chat_message("ai", "📸 截图完成，但没识别到文字"))
                else:
                    self._safe_call(lambda: self._remove_last_thinking())
                    self._safe_call(lambda: self._add_chat_message("ai", "📸 截图已保存"))
            except Exception as e:
                self._safe_call(lambda: self._remove_last_thinking())
                self._safe_call(lambda e=e: self._add_chat_message("error", f"看屏幕失败：{e}"))

        threading.Thread(target=_do, daemon=True).start()

    def _list_windows_result(self):
        if not HAS_WINDOW:
            self._add_chat_message("error", "窗口控制未安装")
            return
        self._add_chat_message("thinking", "📋 正在获取窗口列表...")

        def _do():
            try:
                windows = list_application_windows()
                self._safe_call(lambda: self._remove_last_thinking())
                self._safe_call(lambda: self._add_chat_message("ai", f"📋 当前打开的窗口：\n{windows[:1000]}"))
            except Exception as e:
                self._safe_call(lambda: self._remove_last_thinking())
                self._safe_call(lambda e=e: self._add_chat_message("error", f"获取窗口失败：{e}"))

        threading.Thread(target=_do, daemon=True).start()

    def _mouse_position_result(self):
        if not HAS_WINDOW:
            return

        def _do():
            try:
                pos = get_mouse_position()
                self._safe_call(lambda: self._add_chat_message("ai", f"📍 鼠标位置：({pos[0]}, {pos[1]})"))
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()

    # ── 兼容 FairyBrain 回调 ──

    def _show_result(self, text: str):
        """FairyBrain 回调：显示结果到聊天面板"""
        self._safe_call(lambda: self._remove_last_thinking())
        self._safe_call(lambda: self._add_chat_message("ai", str(text)))

    # ═══════════════════════════════════════════════════════
    #  信息展示
    # ═══════════════════════════════════════════════════════

    def _show_about(self):
        self._ensure_chat_open()
        info = (
            "**AID 桌面精灵 v2**\n\n"
            "暗色磨砂玻璃 · 持续对话 · 语音唤醒\n\n"
            "• 单击球 → 打开对话面板\n"
            "• 语音唤醒「你好 AID」\n"
            "• 支持：截图 / OCR / 窗口控制\n"
        )
        if not HAS_SCREEN:
            info += "• ❌ 截图未安装\n"
        if not HAS_OCR:
            info += "• ❌ OCR 未安装\n"
        if not HAS_WINDOW:
            info += "• ❌ 窗口控制未安装\n"
        self._add_chat_message("ai", info)

    # ═══════════════════════════════════════════════════════
    #  MCP / 退出
    # ═══════════════════════════════════════════════════════

    def _start_mcp_server(self):
        def _run():
            try:
                script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aid_mcp_server.py")
                self._mcp_process = subprocess.Popen(
                    [sys.executable, script, "--transport", "sse", "--port", "8001"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _quit(self):
        if self._mcp_process:
            try:
                self._mcp_process.terminate()
                self._mcp_process.wait(timeout=3)
            except Exception:
                pass
        try:
            self.ball.destroy()
        except Exception:
            pass

    def run(self):
        try:
            self.ball.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self._quit()


# ══════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════


def _safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        try:
            text = " ".join(str(a) for a in args)
            print(text.encode("utf-8", errors="replace").decode("gbk", errors="replace"), **kwargs)
        except Exception:
            pass


def _check_ollama() -> bool:
    """检测本地 Ollama 是否运行"""
    try:
        import json
        import urllib.request

        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            if models:
                _safe_print(f"  Ollama:  ✅ 运行中（模型: {', '.join(models[:3])}）")
                return True
            else:
                _safe_print("  Ollama:  ⏳ 运行中但无模型（运行 ollama pull llama3.2）")
                return True
    except Exception:
        return False


def _env_check():
    """环境检测模式：打印所有能力状态和修复指南"""
    _safe_print("=" * 55)
    _safe_print("  AID 桌面精灵 — 环境检测")
    _safe_print("=" * 55)
    _safe_print()
    _safe_print(f"  Python:    {sys.version.split()[0]}")
    _safe_print(f"  系统:      Windows {sys.getwindowsversion().major}.{sys.getwindowsversion().minor}")
    _safe_print()
    _safe_print("  ── 核心能力 ──")
    _safe_print(f"  窗口系统:  {'✅ Tkinter' if HAS_DWM_ACRYLIC else '✅ Tkinter'}")
    _safe_print(f"  亚克力:    {'✅ 支持' if HAS_DWM_ACRYLIC else '❌ 不支持（Win10 1803+ 才有）'}")
    _safe_print(f"  LLM Key:   {'✅ 已配置' if HAS_LLM else '❌ 未设置'}")
    _safe_print(f"  记忆系统:  {'✅ 就绪' if HAS_MEMORY else '❌ 缺失'}")
    _safe_print()
    _safe_print("  ── 桌面能力 ──")
    _safe_print(f"  截图:      {'✅ 可用' if HAS_SCREEN else '❌ pip install pyautogui pygetwindow Pillow'}")
    _safe_print(f"  OCR:       {'✅ 可用' if HAS_OCR else '❌ pip install pytesseract Pillow'}")
    _safe_print(f"  窗口控制:  {'✅ 可用' if HAS_WINDOW else '❌ pip install pygetwindow'}")
    _safe_print()
    _safe_print("  ── 语音能力 ──")
    _safe_print(f"  语音输入:  {'✅ 可用' if HAS_SPEECH else '❌ pip install SpeechRecognition sounddevice'}")
    _safe_print(f"  语音播报:  {'✅ 可用' if HAS_TTS else '❌ pip install pywin32'}")
    _safe_print()
    _safe_print("  ── 本地 AI 引擎 ──")
    ollama_ok = _check_ollama()
    if not ollama_ok:
        _safe_print("  Ollama:    ❌ 未运行")
        _safe_print("             下载: https://ollama.com/download")
        _safe_print("             然后: ollama pull llama3.2")
    _safe_print()
    _safe_print("  ── LLM 配置 ──")
    if HAS_LLM:
        model = os.getenv("AID_LLM_MODEL", "deepseek-chat（默认）")
        base = os.getenv("DEEPSEEK_API_BASE", "") or os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1（默认）")
        _safe_print(f"  模型:      {model}")
        _safe_print(f"  地址:      {base}")
    else:
        _safe_print("  未配置 API Key，有以下选择：")
        _safe_print("    1. 本地 Ollama（推荐）→ 安装后自动连接")
        _safe_print("    2. DeepSeek → set DEEPSEEK_API_KEY=sk-xxx")
        _safe_print("    3. OpenAI   → set OPENAI_API_KEY=sk-xxx")
    _safe_print()
    _safe_print("  ── 快捷修复 ──")
    _safe_print("  一键安装所有依赖:")
    _safe_print("    scripts\\install_fairy.bat")
    _safe_print()
    _safe_print("  单独安装:")
    missing = []
    if not HAS_SCREEN:
        missing.append("pyautogui pygetwindow Pillow")
    if not HAS_OCR:
        missing.append("pytesseract Pillow")
    if not HAS_SPEECH:
        missing.append("SpeechRecognition sounddevice")
    if missing:
        _safe_print(f"    pip install {' '.join(missing)}")
    _safe_print()
    _safe_print("=" * 55)


def main():
    parser = argparse.ArgumentParser(description="AID 桌面精灵 v2 — 磨砂玻璃悬浮球 + 持续对话")
    parser.add_argument("--version", "-V", action="version", version=f"AID Desktop Fairy v{VERSION}")
    parser.add_argument("--check", action="store_true", help="检测环境并打印安装指南（不启动 GUI）")
    parser.add_argument("--no-mcp", action="store_true", help="不启动 MCP 后台服务器")
    parser.add_argument("--no-brain", action="store_true", help="不加载 LLM 大脑")
    parser.add_argument("--debug", action="store_true", help="输出调试日志")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # ── 环境检测模式 ──
    if args.check:
        _env_check()
        return

    # ── 正常启动 ──
    _safe_print("=" * 50)
    _safe_print("  AID Desktop Fairy v2")
    _safe_print("=" * 50)
    _safe_print()

    # 集中检测一次环境
    _has_ollama = _check_ollama()
    _safe_print()

    _safe_print(f"  Screen:    {'✅' if HAS_SCREEN else '❌'}")
    _safe_print(f"  OCR:       {'✅' if HAS_OCR else '❌'}")
    _safe_print(f"  Window:    {'✅' if HAS_WINDOW else '❌'}")
    _safe_print(f"  Voice:     {'✅' if HAS_SPEECH else '❌'}")
    _safe_print(f"  TTS:       {'✅' if HAS_TTS else '❌'}")
    _safe_print(f"  Acrylic:   {'✅' if HAS_DWM_ACRYLIC else '❌'}")
    _safe_print(f"  Memory:    {'✅' if HAS_MEMORY else '❌'}")
    if HAS_LLM:
        brain_status = "✅"
    elif _has_ollama:
        brain_status = "✅ Ollama"
    else:
        brain_status = "⏳ 未设置 API Key"
    _safe_print(f"  Brain:     {brain_status}")

    _safe_print()
    if not HAS_SCREEN:
        _safe_print("  TIP: 截图 → pip install pyautogui pygetwindow Pillow")
    if not HAS_OCR:
        _safe_print("  TIP: OCR  → pip install pytesseract Pillow")
    if not HAS_SPEECH:
        _safe_print("  TIP: 语音 → pip install SpeechRecognition sounddevice")
    if not HAS_LLM and not _has_ollama:
        _safe_print("  TIP: 本地 AI 免配置 → 安装 Ollama: https://ollama.com")
        _safe_print("       或者设置 DEEPSEEK_API_KEY=sk-xxx")
    _safe_print()
    _safe_print("  单击球 → 打开对话面板")
    _safe_print("  右键 → 快捷菜单")
    _safe_print("  语音唤醒 → 「你好 AID」")
    _safe_print("  拖拽 → 移动位置")
    _safe_print("  环境检测 → --check")
    _safe_print()

    fairy = AIDFairy(no_mcp=args.no_mcp, no_brain=args.no_brain, debug=args.debug)
    fairy.run()


if __name__ == "__main__":
    main()
