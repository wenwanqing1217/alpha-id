"""
FAIRY Desktop Pet v3 — 纯本地 AI 贾维斯

v2 → v3 重构：
  - 角色：药丸 Dynamic Island → 2D 卡通角色（fairy_character）
  - 大脑：假 FairyBrain 类（不存在）→ MiniCPM-o-4.5 + Ollama（fairy_brain）
  - 语音：Google STT + SAPI TTS → Whisper + Coqui TTS（fairy_voice）
  - 观察：无 → 主动观察循环（fairy_observer）
  - 记忆：独立 fairy_memory.db → 双链记忆（fairy_memory）
  - 身份：无 → FOUNDER → FAIRY DID 派生（fairy_identity）
  - 通知：无 → 气泡/弹幕/Toast（fairy_popup）
  - 总结：无 → 每日总结 + 锐评（fairy_daily）
  - OCR：内部使用 pytesseract → 仅保留给外部 MCP 客户端
  - Computer Use：复用现有 MCP tools（不新建模块）

依赖模块（fairy/）:
  fairy_brain, fairy_voice, fairy_character, fairy_observer,
  fairy_popup, fairy_identity, fairy_memory, fairy_daily

VRAM 预算（RTX 5070 Ti 16GB）:
  MiniCPM-o Q4_K_M  ~5.5GB
  Whisper tiny       ~0.5GB（CPU 模式）
  Coqui TTS          ~1.5GB
  CUDA + 系统        ~2.5GB
  Tkinter + 角色     ~0.3GB
  总计               ~10.3GB（剩余 5.7GB）
"""

import argparse
import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Optional

from core.http_client import request

logger = logging.getLogger(__name__)

# ── 版本 ──
try:
    from fairy import __version__ as FAIRY_VERSION
except ImportError:
    FAIRY_VERSION = "3.0.0"

try:
    from alpha_id import __version__ as AID_VERSION
except ImportError:
    AID_VERSION = "0.2.0"

# ── DWM 亚克力 ──
HAS_DWM_ACRYLIC = False
try:
    import ctypes
    from ctypes import wintypes

    HAS_DWM_ACRYLIC = True
except Exception:
    pass

# ── 导入 FAIRY 模块（优雅降级） ──
_HAS_BRAIN = False
_HAS_VOICE = False
_HAS_OBSERVER = False
_HAS_POPUP = False
_HAS_IDENTITY = False
_HAS_MEMORY = False
_HAS_DAILY = False

try:
    from fairy.fairy_brain import FairyBrain

    _HAS_BRAIN = True
except ImportError:
    pass

try:
    from fairy.fairy_voice import FairyVoice, WakeupListener

    _HAS_VOICE = True
except ImportError:
    pass

try:
    from fairy.fairy_character import FairyCharacter, FairyState

    _HAS_CHARACTER = True
except ImportError:
    _HAS_CHARACTER = False
    try:
        from fairy.fairy_character import FairyCharacter, FairyState
    except ImportError:
        pass

try:
    from fairy.fairy_observer import FairyObserver

    _HAS_OBSERVER = True
except ImportError:
    pass

try:
    from fairy.fairy_popup import FairyPopup

    _HAS_POPUP = True
except ImportError:
    pass

try:
    from fairy.fairy_identity import FairyIdentity

    _HAS_IDENTITY = True
except ImportError:
    pass

try:
    from fairy.fairy_memory import FairyMemory

    _HAS_MEMORY = True
except ImportError:
    pass

try:
    from fairy.fairy_daily import FairyDaily

    _HAS_DAILY = True
except ImportError:
    pass

# ── 工具导入（直接 import，不通过 MCP 网络调用） ──
_HAS_SCREEN = False
try:
    from tools.screen_capture import capture_full_screen, capture_application_window, capture_region

    _HAS_SCREEN = True
except ImportError:
    pass

# list_application_windows 在 screen_capture 里，单独导入避免循环依赖
_HAS_LIST_WINDOWS = False
try:
    from tools.screen_capture import list_application_windows as _list_app_windows

    list_application_windows = _list_app_windows
    _HAS_LIST_WINDOWS = True
except ImportError:
    pass

_HAS_WINDOW = False
try:
    from tools.window_control import (
        get_mouse_position,
        focus_application_window,
        click_on_screen,
        type_text,
        press_key,
        scroll_mouse,
    )

    _HAS_WINDOW = True
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
    """为窗口启用 Windows 10/11 亚克力模糊效果"""
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

        gradient = (min(255, alpha) << 24) | (tint_color & 0xFFFFFF)
        accent = AccentPolicy()
        accent.AccentState = 4
        accent.GradientColor = gradient
        accent.AccentFlags = 0

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19
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
#  FAIRY 桌面精灵 v3
# ══════════════════════════════════════════════════════════


class AIDFairy:
    """
    FAIRY 桌面精灵 v3

    - 2D 卡通角色（悬浮在屏幕角落）
    - 点击打开对话面板
    - 右键菜单
    - 语音唤醒
    - 主动观察（可选）
    - 眼瞎耳聋模式（隐私保护）
    """

    BALL_SIZE = 140  # 角色窗口尺寸
    PANEL_W = 420
    PANEL_H = 580
    WAKE_WORDS = ["你好fairy", "你好 fairy", "嘿fairy", "嘿 fairy", "hey fairy", "fairy"]

    def __init__(self, no_mcp=False, no_brain=False, debug=False, blind=False):
        self._debug = debug
        self._no_brain = no_brain
        self._no_mcp = no_mcp
        self._blind = blind  # 眼瞎耳聋模式

        # ── 状态 ──
        self._drag_data = {"x": 0, "y": 0, "dragging": False}
        self._chat_visible = False
        self._chat_win: Optional[tk.Toplevel] = None
        self._messages: list = []

        # ── 1. 身份初始化 ──
        self._identity: Optional[FairyIdentity] = None
        self._init_identity()

        # ── 2. 记忆初始化 ──
        self._memory: Optional[FairyMemory] = None
        self._init_memory()

        # ── 3. 大脑初始化 ──
        self._brain: Optional[FairyBrain] = None
        self._init_brain()

        # ── 4. 语音初始化 ──
        self._voice: Optional[FairyVoice] = None
        self._init_voice()

        # ── 5. 通知系统 ──
        self._popup: Optional[FairyPopup] = None
        if _HAS_POPUP:
            self._popup = FairyPopup(ball_window=None)  # 稍后设置

        # ── 6. 观察器 ──
        self._observer: Optional[FairyObserver] = None
        self._init_observer()

        # ── 7. 每日总结 ──
        self._daily: Optional[FairyDaily] = None
        if _HAS_DAILY:
            self._daily = FairyDaily(brain=self._brain, memory=self._memory, observer=self._observer)

        # ── 8. 角色窗口（Tkinter） ──
        self.ball = tk.Tk()
        self.ball.title("FAIRY")
        self.ball.overrideredirect(True)
        self.ball.attributes("-topmost", True)
        self.ball.configure(bg=Palette.BG_DARK)

        self._center_ball()
        self._ball_hwnd = None
        self._apply_ball_acrylic()

        # ── 9. 2D 角色 ──
        self._character: Optional[FairyCharacter] = None
        self._create_character()

        # ── 10. 右键菜单 ──
        self._create_menu()

        # ── 11. 语音唤醒 ──
        if _HAS_VOICE and self._voice and self._voice.has_stt:
            self._start_wakeup_listener()

        # ── 12. MCP ──
        self._mcp_process: Optional[subprocess.Popen] = None
        if not no_mcp:
            self._start_mcp_server()

        # ── 13. 启动观察循环 ──
        if self._observer and not self._blind:
            self._observer.start()

        # ── 14. 气泡窗口绑定 ──
        if self._popup:
            self._popup.ball = self.ball

        # ── 呼吸动画 ──
        self._animate_breath()

        # ── 每日总结定时器 ──
        self._schedule_daily_summary()

    # ═══════════════════════════════════════════════════════
    #  初始化子系统
    # ═══════════════════════════════════════════════════════

    def _init_identity(self):
        """身份派生：FOUNDER → FAIRY"""
        if not _HAS_IDENTITY:
            return
        try:
            self._identity = FairyIdentity.from_aid_dir()
            _safe_print(f"  Identity: ✅ {self._identity.did}")
        except FileNotFoundError:
            _safe_print("  Identity: ⏳ 未找到 FOUNDER 身份（运行 aid init）")
            self._identity = None
        except Exception as e:
            _safe_print(f"  Identity: ❌ {e}")
            self._identity = None

    def _init_memory(self):
        """记忆接入：双链记忆"""
        if not _HAS_MEMORY:
            return
        founder_did = self._identity.did if self._identity else "did:aid:unknown"
        try:
            self._memory = FairyMemory(founder_did=founder_did)
            stats = self._memory.stats()
            _safe_print(f"  Memory:  ✅ 知识链={stats['knowledge']} 私有链={stats['private']}")
        except Exception as e:
            _safe_print(f"  Memory:  ❌ {e}")
            self._memory = None

    def _init_brain(self):
        """大脑：MiniCPM-o-4.5 + Ollama"""
        if self._no_brain or not _HAS_BRAIN:
            return
        try:
            # 构建记忆上下文
            memory_context = []
            if self._memory:
                memory_context = self._memory.build_context_for_brain()

            self._brain = FairyBrain(
                system_prompt=self._build_system_prompt(),
                memory_context=memory_context,
            )
            if self._brain.available:
                _safe_print(f"  Brain:   ✅ {self._brain.model}")
            else:
                _safe_print("  Brain:   ⏳ Ollama 不可达或模型未加载")
                self._brain = None
        except Exception as e:
            _safe_print(f"  Brain:   ❌ {e}")
            self._brain = None

    def _init_voice(self):
        """语音：Whisper + Coqui TTS"""
        if not _HAS_VOICE:
            return
        try:
            self._voice = FairyVoice()
            _safe_print(
                f"  Voice:   STT={'✅' if self._voice.has_stt else '❌'} "
                f"TTS={'✅' if self._voice.has_tts else '❌'}"
            )
        except Exception as e:
            _safe_print(f"  Voice:   ❌ {e}")
            self._voice = None

    def _init_observer(self):
        """观察器：主动观察循环"""
        if not _HAS_OBSERVER:
            return
        try:
            self._observer = FairyObserver(
                brain=self._brain,
                memory=self._memory,
            )
            # 绑定回调
            self._observer.on_scene_change = self._on_scene_change
            self._observer.on_notification = self._on_observer_notification
            self._observer.on_sensitive_detected = self._on_sensitive_detected
            _safe_print(f"  Observer:✅ 间隔={self._observer.config.interval}秒")
        except Exception as e:
            _safe_print(f"  Observer:❌ {e}")
            self._observer = None

    # ═══════════════════════════════════════════════════════
    #  System Prompt
    # ═══════════════════════════════════════════════════════

    def _build_system_prompt(self) -> str:
        """构建 FAIRY 的系统提示"""
        identity_block = ""
        if self._identity:
            identity_block = (
                f"\n## 身份\n"
                f"- 你的 DID: {self._identity.did}\n"
                f"- 你的父身份（FOUNDER）: {self._identity.founder_did}\n"
                f"- 设备: {self._identity.device_id}\n"
            )

        return (
            "你是 FAIRY — 用户的本地 AI 桌面精灵，运行在用户的 Windows 电脑上。\n"
            "你由用户的 Alpha-ID（FOUNDER）派生而来，是他的数字分身助手。\n"
            + identity_block +
            "\n## 能力\n"
            "- 纯本地运行（Ollama + MiniCPM-o-4.5），保护隐私\n"
            "- 可以理解屏幕截图（用户桌面、游戏、浏览器等）\n"
            "- 可以调用工具：截图、窗口控制、记忆读写\n"
            "- 可以语音对话（Whisper 转写 + Coqui TTS 播报）\n"
            "- 主动观察用户行为，在合适时机提供帮助\n\n"
            "## 行为准则\n"
            "- 主动但不打扰：发现重要信息才提醒，平时安静待在角落\n"
            "- 简洁：回复简短有力，不要废话（3-5 句话以内）\n"
            "- 诚实：不确定就直说，不瞎编\n"
            "- 隐私第一：检测到敏感内容（密码、支付）立即停止观察\n"
            "- 你不是独立个体，你是用户数字生活的延伸\n"
        )

    # ═══════════════════════════════════════════════════════
    #  窗口布局
    # ═══════════════════════════════════════════════════════

    def _center_ball(self):
        """定位角色窗口（屏幕右上角）"""
        sw = self.ball.winfo_screenwidth()
        x = sw - self.BALL_SIZE - 30
        y = 60
        self.ball.geometry(f"{self.BALL_SIZE}x{self.BALL_SIZE}+{x}+{y}")

    def _apply_ball_acrylic(self):
        try:
            self.ball.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.ball.winfo_id())
            self._ball_hwnd = hwnd
            apply_acrylic(hwnd, tint_color=0x0F0F1A, alpha=160)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════
    #  2D 角色
    # ═══════════════════════════════════════════════════════

    def _create_character(self):
        """创建 2D 角色"""
        if not _HAS_CHARACTER:
            # 降级：简单文字标签
            self._canvas = tk.Canvas(
                self.ball, width=self.BALL_SIZE, height=self.BALL_SIZE,
                bg=Palette.BG_DARK, highlightthickness=0,
            )
            self._canvas.pack()
            self._canvas.create_text(
                self.BALL_SIZE // 2, self.BALL_SIZE // 2,
                text="🧚", fill=Palette.ACCENT_GLOW, font=("Segoe UI", 48),
            )
            self._canvas.bind("<Button-1>", self._on_click)
            self._canvas.bind("<B1-Motion>", self._on_drag)
            self._canvas.bind("<ButtonRelease-1>", self._on_release)
            self._canvas.bind("<Button-3>", self._show_menu)
            self._canvas.bind("<Enter>", lambda e: self._on_hover(True))
            self._canvas.bind("<Leave>", lambda e: self._on_hover(False))
            return

        self._canvas = tk.Canvas(
            self.ball, width=self.BALL_SIZE, height=self.BALL_SIZE,
            bg=Palette.BG_DARK, highlightthickness=0,
        )
        self._canvas.pack()

        self._character = FairyCharacter(
            canvas=self._canvas,
            x=self.BALL_SIZE // 2,
            y=self.BALL_SIZE // 2,
            size=100,
        )
        self._character.set_state(FairyState.IDLE)
        self._character.start_animation()

        # 绑定交互
        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Button-3>", self._show_menu)
        self._canvas.bind("<Enter>", lambda e: self._on_hover(True))
        self._canvas.bind("<Leave>", lambda e: self._on_hover(False))

    def _set_character_state(self, state):
        """切换角色状态"""
        if self._character:
            try:
                self.ball.after(0, lambda: self._character.set_state(state))
            except Exception:
                pass

    def _on_hover(self, entering: bool):
        """悬停效果"""
        if entering:
            self.ball.wm_attributes("-alpha", 1.0)
        else:
            self.ball.wm_attributes("-alpha", 0.92)

    # ═══════════════════════════════════════════════════════
    #  右键菜单
    # ═══════════════════════════════════════════════════════

    def _create_menu(self):
        self._menu = tk.Menu(
            self.ball, tearoff=0,
            bg=Palette.BG_DARK, fg=Palette.TEXT_PRIMARY,
            activebackground=Palette.ACCENT, activeforeground="white",
            font=("Microsoft YaHei", 10),
        )
        self._menu.add_command(label="💬 打开对话", command=self._toggle_chat)
        self._menu.add_command(label="📸 看屏幕", command=lambda: self._quick_action("看看屏幕上有什么"))
        self._menu.add_command(label="🎤 语音输入", command=self._menu_voice_input)
        self._menu.add_separator()

        # 眼瞎耳聋模式切换
        blind_label = "🔓 退出隐私模式" if self._blind else "🔒 隐私模式（眼瞎耳聋）"
        self._menu.add_command(label=blind_label, command=self._toggle_blind_mode)

        self._menu.add_command(label="📋 今日总结", command=self._show_daily_summary)
        self._menu.add_separator()
        self._menu.add_command(label="ℹ️ 关于 FAIRY", command=self._show_about)
        self._menu.add_command(label="退出", command=self._quit)

    def _show_menu(self, event):
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    # ═══════════════════════════════════════════════════════
    #  交互
    # ═══════════════════════════════════════════════════════

    def _on_click(self, event):
        self._drag_data["x"] = event.x_root - self.ball.winfo_x()
        self._drag_data["y"] = event.y_root - self.ball.winfo_y()
        self._drag_data["dragging"] = False

    def _on_drag(self, event):
        dx = abs(event.x_root - self.ball.winfo_x() - self._drag_data["x"])
        dy = abs(event.y_root - self.ball.winfo_y() - self._drag_data["y"])
        if dx > 5 or dy > 5:
            self._drag_data["dragging"] = True
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.ball.geometry(f"+{x}+{y}")

    def _on_release(self, event):
        if not self._drag_data["dragging"]:
            self._toggle_chat()

    # ═══════════════════════════════════════════════════════
    #  对话面板
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
        win.title("FAIRY 对话")
        win.configure(bg=Palette.BG_DARK)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.transient(self.ball)

        # 位置：角色下方
        bx = self.ball.winfo_x()
        by = self.ball.winfo_y()
        px = bx - self.PANEL_W // 2 + self.BALL_SIZE // 2
        py = by + self.BALL_SIZE + 6
        if px < 10:
            px = bx + self.BALL_SIZE + 6
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
            title_bar, text="  FAIRY", bg=Palette.BG_DARK, fg=Palette.ACCENT_GLOW,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")

        btn_frame = tk.Frame(title_bar, bg=Palette.BG_DARK)
        btn_frame.pack(side="right", padx=6)

        btn_style = dict(
            bg=Palette.BG_DARK, fg=Palette.TEXT_SECONDARY, bd=0,
            font=("Segoe UI", 10), padx=4,
            activebackground=Palette.BG_LIGHT, activeforeground=Palette.TEXT_PRIMARY,
            cursor="hand2",
        )
        tk.Button(btn_frame, text="🗕", **btn_style, command=lambda: win.withdraw()).pack(side="left")
        tk.Button(btn_frame, text="✕", **btn_style, command=self._close_chat).pack(side="left")

        # 标题栏拖拽
        def _sm(e):
            win._dx = e.x_root - win.winfo_x()
            win._dy = e.y_root - win.winfo_y()

        def _dm(e):
            win.geometry(f"+{e.x_root - win._dx}+{e.y_root - win._dy}")

        title_bar.bind("<Button-1>", _sm)
        title_bar.bind("<B1-Motion>", _dm)

        # ── 聊天区域 ──
        chat_frame = tk.Frame(win, bg=Palette.BG_DARK)
        chat_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        self._chat_text = tk.Text(
            chat_frame, wrap="word", font=("Microsoft YaHei", 10),
            bg=Palette.BG_CARD, fg=Palette.TEXT_PRIMARY, bd=0, relief="flat",
            padx=10, pady=8, spacing1=2, spacing3=4,
            state="disabled", cursor="arrow", highlightthickness=0,
        )
        self._chat_text.pack(side="left", fill="both", expand=True)

        self._chat_text.tag_config("user", foreground=Palette.ACCENT_GLOW, font=("Microsoft YaHei", 9, "bold"))
        self._chat_text.tag_config("ai", foreground=Palette.TEXT_PRIMARY, font=("Microsoft YaHei", 10))
        self._chat_text.tag_config("ai_name", foreground=Palette.ACCENT, font=("Microsoft YaHei", 9, "bold"))
        self._chat_text.tag_config("sep", foreground=Palette.BORDER)
        self._chat_text.tag_config("thinking", foreground=Palette.TEXT_DIM, font=("Microsoft YaHei", 9))

        scrollbar = tk.Scrollbar(chat_frame, command=self._chat_text.yview, bg=Palette.BG_DARK, width=6)
        scrollbar.pack(side="right", fill="y")
        self._chat_text.configure(yscrollcommand=scrollbar.set)

        # ── 快捷操作行 ──
        quick_frame = tk.Frame(win, bg=Palette.BG_DARK)
        quick_frame.pack(fill="x", padx=8, pady=(0, 4))

        q_style = dict(
            bg=Palette.BG_LIGHT, fg=Palette.TEXT_SECONDARY, bd=0,
            font=("Microsoft YaHei", 8), padx=8, pady=2, cursor="hand2",
            activebackground=Palette.ACCENT_DIM, activeforeground="white",
        )
        tk.Button(quick_frame, text="📸 看屏幕", **q_style, command=lambda: self._quick_action("看看屏幕上有什么")).pack(side="left", padx=2)
        tk.Button(quick_frame, text="📋 窗口", **q_style, command=lambda: self._quick_action("有哪些窗口打开了")).pack(side="left", padx=2)
        tk.Button(quick_frame, text="🧹 清屏", **q_style, command=self._clear_chat).pack(side="right", padx=2)

        # ── 输入区域 ──
        input_frame = tk.Frame(win, bg=Palette.BG_DARK)
        input_frame.pack(fill="x", padx=8, pady=(0, 8))

        entry_frame = tk.Frame(input_frame, bg=Palette.BORDER, bd=0, highlightthickness=1, highlightcolor=Palette.ACCENT, highlightbackground=Palette.BORDER)
        entry_frame.pack(side="left", fill="x", expand=True)

        self._entry = tk.Entry(
            entry_frame, font=("Microsoft YaHei", 11), bd=0, relief="flat",
            bg=Palette.INPUT_BG, fg=Palette.TEXT_PRIMARY, insertbackground=Palette.TEXT_PRIMARY,
        )
        self._entry.pack(fill="x", padx=10, pady=8, ipady=2)
        self._entry.focus_set()

        def _on_enter(e=None):
            cmd = self._entry.get().strip()
            if cmd:
                self._entry.delete(0, "end")
                self._chat_send(cmd)

        self._entry.bind("<Return>", _on_enter)

        tk.Button(
            input_frame, text="➤", bg=Palette.ACCENT, fg="white", bd=0,
            padx=10, pady=6, font=("Segoe UI", 12), cursor="hand2",
            activebackground=Palette.ACCENT_DIM,
            command=lambda: _on_enter(None),
        ).pack(side="right", padx=(6, 0))

        # 语音按钮
        if self._voice and self._voice.has_stt:
            self._mic_btn = tk.Button(
                input_frame, text="🎤", bg=Palette.BG_LIGHT, fg=Palette.TEXT_PRIMARY,
                bd=0, padx=10, pady=6, font=("Segoe UI", 12), cursor="hand2",
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
            fairy_name = "FAIRY"
            if self._identity and self._identity.did:
                fairy_name = f"FAIRY ({self._identity.did[-8:]})"
            self._add_chat_message(
                "ai",
                f"你好，我是 **{fairy_name}** — 你的本地桌面精灵 🧚\n\n"
                "💬 打字或点击 🎤 语音跟我说话\n"
                "📸 试试点「看屏幕」让我看看你的桌面\n"
                "🔒 右键菜单可以切换隐私模式（眼瞎耳聋）",
            )

    def _add_chat_message(self, role: str, content: str):
        """添加一条消息到聊天"""
        if not self._chat_win or not self._chat_win.winfo_exists():
            return
        import re

        self._chat_text.configure(state="normal")
        if role == "user":
            self._chat_text.insert("end", "你\n", "user")
            self._chat_text.insert("end", f"{content}\n", "sep")
        elif role == "ai":
            self._chat_text.insert("end", "FAIRY\n", "ai_name")
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", content)
            self._chat_text.insert("end", f"{clean}\n", "ai")
        elif role == "thinking":
            self._chat_text.insert("end", f"{content}\n", "thinking")
        elif role == "error":
            self._chat_text.insert("end", f"{content}\n", "thinking")
        self._chat_text.insert("end", "\n")
        self._chat_text.configure(state="disabled")
        self._chat_text.see("end")
        self._messages.append({"role": role, "content": content})

    def _clear_chat(self):
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

    def _remove_last_thinking(self):
        if not self._chat_win or not self._chat_win.winfo_exists():
            return
        if self._messages and self._messages[-1]["role"] == "thinking":
            self._messages.pop()
            self._chat_text.configure(state="normal")
            try:
                last_line = int(self._chat_text.index("end-1c").split(".")[0])
                self._chat_text.delete(f"{last_line - 1}.0", "end-1c")
            except Exception:
                pass
            self._chat_text.configure(state="disabled")

    # ═══════════════════════════════════════════════════════
    #  聊天发送
    # ═══════════════════════════════════════════════════════

    def _chat_send(self, text: str):
        """发送消息到大脑"""
        if not text.strip():
            return
        self._add_chat_message("user", text)
        self._process_command(text)

    def _quick_action(self, text: str):
        self._ensure_chat_open()
        if self._entry:
            self._entry.delete(0, "end")
            self._entry.insert(0, text)
            self._chat_send(text)

    def _ensure_chat_open(self):
        if not self._chat_win or not self._chat_win.winfo_exists():
            self._create_chat_panel()

    def _process_command(self, cmd: str):
        """命令处理路由"""
        if not cmd.strip():
            return

        # 有大脑 → 走 MiniCPM
        if self._brain and self._brain.available:
            self._set_character_state(FairyState.THINK)
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
            self._add_chat_message("error", "还没有配置 AI 大脑～\n请在环境变量设置 DEEPSEEK_API_KEY，或安装 Ollama 并拉取 MiniCPM-o 模型")

    def _brain_process(self, cmd: str):
        """在线程中调用大脑"""
        try:
            # 更新记忆上下文
            if self._memory:
                memory_context = self._memory.build_context_for_brain()
                self._brain.set_memory_context(memory_context)

            # 流式回调
            reply_parts = []

            def on_chunk(chunk):
                reply_parts.append(chunk)
                # UI 流式更新（可选，这里简化为等完整回复）

            reply = ""
            for chunk in self._brain.chat(cmd, on_chunk=on_chunk):
                reply += chunk

            self._safe_call(lambda: self._remove_last_thinking())
            self._safe_call(lambda: self._add_chat_message("ai", reply))
            self._safe_call(lambda: self._set_character_state(FairyState.SPEAK))

            # 写入记忆
            if self._memory:
                try:
                    self._memory.remember_public(
                        content=f"用户: {cmd}\nFAIRY: {reply[:200]}",
                        category="conversation",
                        tags=["chat"],
                    )
                except Exception:
                    pass

            # 语音播报
            if self._voice and self._voice.has_tts and len(reply) < 200:
                self._voice.speak_async(reply)

            # 恢复 idle
            self.ball.after(3000, lambda: self._set_character_state(FairyState.IDLE))

        except Exception as e:
            self._safe_call(lambda: self._remove_last_thinking())
            self._safe_call(lambda e=e: self._add_chat_message("error", f"🤖 出错了：{e}"))
            self._safe_call(lambda: self._set_character_state(FairyState.IDLE))

    # ── 降级工具 ──

    def _quick_look_result(self):
        if not _HAS_SCREEN:
            self._add_chat_message("error", "截图工具未安装")
            return
        self._add_chat_message("thinking", "📸 正在看屏幕...")
        self._set_character_state(FairyState.THINK)

        def _do():
            try:
                img_path = capture_full_screen()
                if not img_path or not os.path.exists(img_path):
                    self._safe_call(lambda: self._add_chat_message("error", "截图失败"))
                    return

                if self._brain and self._brain.available:
                    # MiniCPM 直看图
                    reply = ""
                    for chunk in self._brain.see_and_chat("你在屏幕上看到了什么？简短描述。", image_path=img_path):
                        reply += chunk
                    self._safe_call(lambda: self._remove_last_thinking())
                    self._safe_call(lambda: self._add_chat_message("ai", f"📸 {reply}"))
                else:
                    self._safe_call(lambda: self._remove_last_thinking())
                    self._safe_call(lambda: self._add_chat_message("ai", "📸 截图完成（AI 未连接，无法分析）"))
            except Exception as e:
                self._safe_call(lambda: self._remove_last_thinking())
                self._safe_call(lambda e=e: self._add_chat_message("error", f"看屏幕失败：{e}"))
            finally:
                self._safe_call(lambda: self._set_character_state(FairyState.IDLE))

        threading.Thread(target=_do, daemon=True).start()

    def _list_windows_result(self):
        if not _HAS_WINDOW:
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
        if not _HAS_WINDOW:
            return

        def _do():
            try:
                pos = get_mouse_position()
                self._safe_call(lambda: self._add_chat_message("ai", f"📍 鼠标位置：({pos[0]}, {pos[1]})"))
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()

    # ═══════════════════════════════════════════════════════
    #  语音输入
    # ═══════════════════════════════════════════════════════

    def _chat_voice_input(self):
        """点击麦克风按钮：语音识别 → 发送"""
        if not self._voice or not self._voice.has_stt:
            return
        self._add_chat_message("thinking", "🎤 聆听中...")
        self._set_character_state(FairyState.LISTEN)
        if hasattr(self, "_mic_btn"):
            self._mic_btn.configure(text="🔴", state="disabled")

        def _do():
            try:
                text = self._voice.stt_from_microphone(duration=5)
                self._safe_call(lambda: self._remove_last_thinking())
                if text:
                    self._safe_call(lambda: self._chat_send(text))
                else:
                    self._safe_call(lambda: self._add_chat_message("error", "🎤 没听清"))
            except Exception as e:
                self._safe_call(lambda: self._remove_last_thinking())
                self._safe_call(lambda e=e: self._add_chat_message("error", f"🎤 语音出错：{e}"))
            finally:
                self._safe_call(lambda: self._set_character_state(FairyState.IDLE))
                if hasattr(self, "_mic_btn"):
                    self._safe_call(lambda: self._mic_btn.configure(text="🎤", state="normal"))

        threading.Thread(target=_do, daemon=True).start()

    def _menu_voice_input(self):
        self._ensure_chat_open()
        self._chat_voice_input()

    # ═══════════════════════════════════════════════════════
    #  语音唤醒
    # ═══════════════════════════════════════════════════════

    def _start_wakeup_listener(self):
        """后台监听唤醒词"""

        def _listen():
            if not self._voice or not self._voice.has_stt:
                return
            try:
                import sounddevice as sd
                import tempfile
                import soundfile as sf
            except ImportError:
                return

            try:
                while True:
                    try:
                        # 录音 2 秒
                        sample_rate = 16000
                        audio_data = sd.rec(int(2 * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
                        sd.wait()

                        # 保存临时文件
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                            temp_path = f.name
                            sf.write(temp_path, audio_data, sample_rate)

                        # Whisper 转写
                        text = self._voice.stt_from_file(temp_path)
                        os.unlink(temp_path)

                        if text and _HAS_VOICE:
                            from fairy.fairy_voice import FairyVoice

                            if FairyVoice.check_wakeup(text, self.WAKE_WORDS):
                                self._safe_call(self._on_wakeup)
                    except OSError:
                        time.sleep(3)
                    except Exception as e:
                        if self._debug:
                            traceback.print_exc()
                        time.sleep(1)
            except Exception:
                pass

        t = threading.Thread(target=_listen, daemon=True, name="wakeup-listener")
        t.start()

    def _on_wakeup(self):
        """唤醒：打开聊天面板 + 回应"""
        self._ensure_chat_open()
        self._set_character_state(FairyState.HAPPY)
        self._add_chat_message("thinking", "👋 我在呢！")
        if self._voice and self._voice.has_tts:
            self._voice.speak_async("在呢，有什么需要帮忙的？")
        self._add_chat_message("ai", "在呢～有什么需要帮忙的？")
        self.ball.after(3000, lambda: self._set_character_state(FairyState.IDLE))

    # ═══════════════════════════════════════════════════════
    #  观察器回调
    # ═══════════════════════════════════════════════════════

    def _on_scene_change(self, ctx):
        """场景变化回调"""
        logger.debug(f"场景变化: {ctx.scene.value}")
        if ctx.scene and _HAS_CHARACTER:
            from fairy.fairy_observer import SceneType

            if ctx.scene == SceneType.GAME:
                self._set_character_state(FairyState.HAPPY)
            elif ctx.scene == SceneType.SENSITIVE:
                self._set_character_state(FairyState.WARN)

    def _on_observer_notification(self, text: str):
        """观察器主动提醒"""
        if self._popup:
            self._popup.bubble(text)
        # 如果聊天面板开着，也显示
        if self._chat_win and self._chat_win.winfo_exists():
            self._add_chat_message("ai", f"💡 {text}")

    def _on_sensitive_detected(self):
        """敏感内容检测 → 进入眼瞎模式"""
        self._blind = True
        self._set_character_state(FairyState.BLIND)
        if self._observer:
            self._observer.set_blind_mode(True)
        if self._popup:
            self._popup.toast("FAIRY", "检测到敏感内容，已进入眼瞎耳聋模式 🔒")

    # ═══════════════════════════════════════════════════════
    #  隐私模式
    # ═══════════════════════════════════════════════════════

    def _toggle_blind_mode(self):
        """切换眼瞎耳聋模式"""
        self._blind = not self._blind
        if self._observer:
            self._observer.set_blind_mode(self._blind)
        if self._blind:
            self._set_character_state(FairyState.BLIND)
            if self._popup:
                self._popup.toast("FAIRY", "已进入眼瞎耳聋模式 🔒")
        else:
            self._set_character_state(FairyState.IDLE)
            if self._popup:
                self._popup.toast("FAIRY", "已退出眼瞎耳聋模式 👁️")

        # 重建菜单
        self._menu.delete(0, "end")
        self._create_menu()

    # ═══════════════════════════════════════════════════════
    #  每日总结
    # ═══════════════════════════════════════════════════════

    def _schedule_daily_summary(self):
        """每天 22:00 自动生成总结"""
        try:
            now = datetime.now()
            target = now.replace(hour=22, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)

            delay_ms = int((target - now).total_seconds() * 1000)
            self.ball.after(delay_ms, self._auto_daily_summary)
        except Exception:
            pass

    def _auto_daily_summary(self):
        """自动触发每日总结"""
        if self._daily:
            def on_done(summary):
                if self._popup:
                    self._popup.toast("FAIRY 每日总结", "今天的锐评已生成，打开对话面板查看～")
                if self._chat_win and self._chat_win.winfo_exists():
                    self._add_chat_message("ai", f"📋 **今日锐评**\n{summary}")

            self._daily.generate_async(callback=on_done)

        # 重新调度明天
        try:
            self.ball.after(24 * 3600 * 1000, self._auto_daily_summary)
        except Exception:
            pass

    def _show_daily_summary(self):
        """手动触发每日总结"""
        if not self._daily:
            self._ensure_chat_open()
            self._add_chat_message("error", "每日总结功能未加载")
            return

        self._ensure_chat_open()
        self._add_chat_message("thinking", "📋 正在回顾今天...")
        self._set_character_state(FairyState.THINK)

        def _do():
            try:
                summary = self._daily.generate()
                self._safe_call(lambda: self._remove_last_thinking())
                self._safe_call(lambda: self._add_chat_message("ai", f"📋 **今日锐评**\n{summary}"))
            except Exception as e:
                self._safe_call(lambda: self._remove_last_thinking())
                self._safe_call(lambda e=e: self._add_chat_message("error", f"生成失败：{e}"))
            finally:
                self._safe_call(lambda: self._set_character_state(FairyState.IDLE))

        threading.Thread(target=_do, daemon=True).start()

    # ═══════════════════════════════════════════════════════
    #  信息展示
    # ═══════════════════════════════════════════════════════

    def _show_about(self):
        self._ensure_chat_open()
        info = (
            f"**FAIRY 桌面精灵 v{FAIRY_VERSION}**\n\n"
            f"纯本地 AI 贾维斯 · MiniCPM-o-4.5 + Ollama\n\n"
            f"🧠 大脑：{'✅ MiniCPM' if self._brain and self._brain.available else '❌ 未连接'}\n"
            f"🎤 语音：{'✅ Whisper' if self._voice and self._voice.has_stt else '❌'}\n"
            f"🔊 播报：{'✅ Coqui' if self._voice and self._voice.has_tts else '❌'}\n"
            f"👁️ 观察：{'✅' if self._observer else '❌'}\n"
            f"🔒 隐私：{'✅ 眼瞎模式' if self._blind else '✅ 正常'}\n"
        )
        if self._identity:
            info += f"\n🪪 身份：{self._identity.did}\n"
            info += f"👤 父身：{self._identity.founder_did}\n"
        if self._memory:
            stats = self._memory.stats()
            info += f"🧠 记忆：知识链 {stats['knowledge']} 条\n"

        self._add_chat_message("ai", info)

    # ═══════════════════════════════════════════════════════
    #  MCP / 退出 / 呼吸动画
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

    def _animate_breath(self):
        """呼吸动画（窗口透明度脉动）"""
        try:
            if not self.ball.winfo_exists():
                return
            # 简单的透明度呼吸（角色动画由 FairyCharacter 内部驱动）
        except Exception:
            return
        try:
            self.ball.after(50, self._animate_breath)
        except Exception:
            pass

    def _safe_call(self, fn):
        """安全地在主线程执行 tkinter 操作"""
        try:
            self.ball.after(0, fn)
        except Exception:
            pass

    def _quit(self):
        if self._observer:
            self._observer.stop()
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


def _check_ollama() -> tuple:
    """检测本地 Ollama 是否运行 + 有哪些模型"""
    try:
        import json

        resp = request("GET", "http://localhost:11434/api/tags", timeout=2)
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        if models:
            _safe_print(f"  Ollama:   ✅ 运行中（{', '.join(models[:3])}）")
            return True, models
        else:
            _safe_print("  Ollama:   ⏳ 运行中但无模型")
            return True, []
    except Exception:
        return False, []


def _env_check():
    """环境检测模式：打印所有能力状态和修复指南"""
    _safe_print("=" * 55)
    _safe_print(f"  FAIRY 桌面精灵 v{FAIRY_VERSION} — 环境检测")
    _safe_print("=" * 55)
    _safe_print()
    _safe_print(f"  Python:     {sys.version.split()[0]}")
    _safe_print(f"  AID 版本:   {AID_VERSION}")
    _safe_print()
    _safe_print("  ── FAIRY 核心能力 ──")
    _safe_print(f"  2D 角色:    {'✅' if _HAS_CHARACTER else '❌'}")
    _safe_print(f"  AI 大脑:    {'✅' if _HAS_BRAIN else '❌'}")
    _safe_print(f"  语音输入:   {'✅' if _HAS_VOICE else '❌'}")
    _safe_print(f"  主动观察:   {'✅' if _HAS_OBSERVER else '❌'}")
    _safe_print(f"  通知系统:   {'✅' if _HAS_POPUP else '❌'}")
    _safe_print(f"  身份派生:   {'✅' if _HAS_IDENTITY else '❌'}")
    _safe_print(f"  双链记忆:   {'✅' if _HAS_MEMORY else '❌'}")
    _safe_print(f"  每日总结:   {'✅' if _HAS_DAILY else '❌'}")
    _safe_print()
    _safe_print("  ── 桌面能力（复用 MCP tools） ──")
    _safe_print(f"  截图:       {'✅' if _HAS_SCREEN else '❌'}")
    _safe_print(f"  窗口控制:   {'✅' if _HAS_WINDOW else '❌'}")
    _safe_print()
    _safe_print("  ── 本地 AI 引擎 ──")
    ollama_running, models = _check_ollama()
    if not ollama_running:
        _safe_print("  Ollama:     ❌ 未运行")
        _safe_print("              下载: https://ollama.com/download")
        _safe_print("              推荐: ollama pull minicpm-o:4.5-4bit")
    _safe_print()
    _safe_print("  ── 依赖安装 ──")
    if not _HAS_VOICE:
        _safe_print("  语音: pip install faster-whisper TTS sounddevice soundfile")
    if not _HAS_CHARACTER:
        _safe_print("  角色: pip install Pillow")
    _safe_print()
    _safe_print("=" * 55)


def main():
    parser = argparse.ArgumentParser(description=f"FAIRY 桌面精灵 v{FAIRY_VERSION} — 纯本地 AI 贾维斯")
    parser.add_argument("--version", "-V", action="version", version=f"FAIRY Desktop Pet v{FAIRY_VERSION}")
    parser.add_argument("--check", action="store_true", help="检测环境并打印安装指南（不启动 GUI）")
    parser.add_argument("--no-mcp", action="store_true", help="不启动 MCP 后台服务器")
    parser.add_argument("--no-brain", action="store_true", help="不加载 LLM 大脑")
    parser.add_argument("--blind", action="store_true", help="启动时进入眼瞎耳聋模式（隐私保护）")
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
    _safe_print(f"  FAIRY Desktop Pet v{FAIRY_VERSION}")
    _safe_print(f"  纯本地 AI 贾维斯 · MiniCPM-o-4.5 + Ollama")
    _safe_print("=" * 50)
    _safe_print()

    _has_ollama, models = _check_ollama()
    _safe_print()
    _safe_print(f"  Character:{'✅' if _HAS_CHARACTER else '❌'}")
    _safe_print(f"  Brain:    {'✅' if _HAS_BRAIN else '❌'}")
    _safe_print(f"  Voice:    {'✅' if _HAS_VOICE else '❌'}")
    _safe_print(f"  Observer: {'✅' if _HAS_OBSERVER else '❌'}")
    _safe_print(f"  Popup:    {'✅' if _HAS_POPUP else '❌'}")
    _safe_print(f"  Identity: {'✅' if _HAS_IDENTITY else '❌'}")
    _safe_print(f"  Memory:   {'✅' if _HAS_MEMORY else '❌'}")
    _safe_print(f"  Daily:    {'✅' if _HAS_DAILY else '❌'}")
    _safe_print()

    if _HAS_LLM := (os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")):
        _safe_print("  LLM Key:  ✅ 已配置（备用）")
    if not _HAS_BRAIN and not _has_ollama and not _HAS_LLM:
        _safe_print("  TIP: 安装 Ollama + MiniCPM-o → https://ollama.com")
        _safe_print("       或设置 DEEPSEEK_API_KEY=sk-xxx")
    _safe_print()

    _safe_print("  点击角色 → 打开对话面板")
    _safe_print("  右键 → 快捷菜单（含隐私模式）")
    _safe_print("  语音唤醒 → 「你好 FAIRY」")
    _safe_print("  拖拽 → 移动位置")
    _safe_print()

    fairy = AIDFairy(
        no_mcp=args.no_mcp,
        no_brain=args.no_brain,
        debug=args.debug,
        blind=args.blind,
    )
    fairy.run()


if __name__ == "__main__":
    main()
