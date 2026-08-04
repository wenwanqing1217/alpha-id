"""
NURO 桌面精灵 v3 — 主应用类（AidNuro）

纯本地 AI 贾维斯，运行在 Windows 桌面上的悬浮精灵。

架构（重构后）：
  - feature_flags.py  → 所有 _HAS_* 标志和可选模块导入
  - palette.py        → UI 调色板
  - acrylic.py        → DWM 亚克力效果
  - daily_summary.py  → 每日总结调度（含 timedelta bug 修复）
  - cli.py            → CLI 入口和 main()
  - app.py (本文件)   → AidNuro 主类

启动顺序（__init__ 中的 14 步）：
  1. 身份初始化（FOUNDER → NURO DID）
  2. 记忆接入（双链记忆）
  3. 大脑（MiniCPM-o + Ollama）
  4. 语音（Whisper + Coqui TTS）
  5. 通知气泡
  6. 主动观察器
  7. 每日总结
  8. Tkinter 角色窗口
  9. 2D 角色（FairyCharacter 或降级为 emoji）
  10. 右键菜单
  11. 语音唤醒监听
  12. MCP 后台服务器
  13. 启动观察循环
  14. 气泡绑定 + 呼吸动画 + 每日总结定时器

VRAM 预算（RTX 5070 Ti 16GB）：
  MiniCPM-o Q4_K_M  ~5.5GB
  Whisper tiny       ~0.5GB（CPU 模式）
  Coqui TTS          ~1.5GB
  CUDA + 系统        ~2.5GB
  Tkinter + 角色     ~0.3GB
  总计               ~10.3GB（剩余 5.7GB）
"""

import ctypes
import logging
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Optional

# ── 子模块导入 ──
# 注意：功能标志通过模块引用（而非 from import），使单元测试可以 monkeypatch
from entrypoints import feature_flags
from entrypoints.acrylic import apply_acrylic
from entrypoints.daily_summary import compute_next_summary_delay_ms
from entrypoints.feature_flags import (  # noqa: F401 — 保持向后兼容的 re-export
    AID_VERSION,
    NURO_VERSION,
)
from entrypoints.palette import Palette
from entrypoints.cli import _safe_print

# ── 便捷别名（保持向后兼容） ──
# 新代码应直接使用 feature_flags._HAS_*
_HAS_BRAIN = feature_flags._HAS_BRAIN
_HAS_VOICE = feature_flags._HAS_VOICE
_HAS_CHARACTER = feature_flags._HAS_CHARACTER
_HAS_OBSERVER = feature_flags._HAS_OBSERVER
_HAS_POPUP = feature_flags._HAS_POPUP
_HAS_IDENTITY = feature_flags._HAS_IDENTITY
_HAS_MEMORY = feature_flags._HAS_MEMORY
_HAS_DAILY = feature_flags._HAS_DAILY
_HAS_SCREEN = feature_flags._HAS_SCREEN
_HAS_WINDOW = feature_flags._HAS_WINDOW
_HAS_LIST_WINDOWS = feature_flags._HAS_LIST_WINDOWS

logger = logging.getLogger(__name__)

# ── Tkinter ──
try:
    import tkinter as tk
except ImportError:
    sys.exit("tkinter 不可用。请安装 Python 时勾选 'tcl/tk and IDLE'。")


class AidNuro:
    """
    NURO 桌面精灵 v3

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
    WAKE_WORDS = ["你好nuro", "你好 nuro", "嘿nuro", "嘿 nuro", "hey nuro", "nuro"]

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
        self._floating = False  # 悬浮模式：窗口隐藏但进程存活

        # ── 1. 身份初始化 ──
        self._identity: Optional[FairyIdentity] = None
        self._init_identity()

        # ── 2. 记忆初始化 ──
        self._memory: Optional[FairyMemory] = None
        self._init_memory()

        # ── 3. 大脑初始化 ──
        self._brain = None  # Optional[FairyBrain]
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
        self.ball.title("NURO")
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
        """身份派生：FOUNDER → NURO"""
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

            from fairy.fairy_brain import FairyBrain

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
        """构建 NURO 的系统提示"""
        identity_block = ""
        if self._identity:
            identity_block = (
                f"\n## 身份\n"
                f"- 你的 DID: {self._identity.did}\n"
                f"- 你的父身份（FOUNDER）: {self._identity.founder_did}\n"
                f"- 设备: {self._identity.device_id}\n"
            )

        return (
            "你是 NURO — 用户的本地 AI 桌面精灵，运行在用户的 Windows 电脑上。\n"
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
        """定位角色窗口（左下角，可拖拽移动）"""
        sw = self.ball.winfo_screenwidth()
        sh = self.ball.winfo_screenheight()
        x = 30
        y = sh - self.BALL_SIZE - 60  # 底部偏上，避开任务栏
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
        self._menu.add_command(label="📌 悬浮模式", command=self._toggle_floating)
        self._menu.add_separator()

        # 眼瞎耳聋模式切换
        blind_label = "🔓 退出隐私模式" if self._blind else "🔒 隐私模式（眼瞎耳聋）"
        self._menu.add_command(label=blind_label, command=self._toggle_blind_mode)

        self._menu.add_command(label="📋 今日总结", command=self._show_daily_summary)
        self._menu.add_separator()
        self._menu.add_command(label="ℹ️ 关于 NURO Ghost", command=self._show_about)
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
        win.title("NURO 对话")
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
            title_bar, text="  NURO", bg=Palette.BG_DARK, fg=Palette.ACCENT_GLOW,
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
            fairy_name = "NURO"
            if self._identity and self._identity.did:
                fairy_name = f"NURO ({self._identity.did[-8:]})"
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

        self._chat_text.configure(state="normal")
        if role == "user":
            self._chat_text.insert("end", "你\n", "user")
            self._chat_text.insert("end", f"{content}\n", "sep")
        elif role == "ai":
            self._chat_text.insert("end", "NURO\n", "ai_name")
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
                        content=f"用户: {cmd}\nNURO: {reply[:200]}",
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
            self._popup.toast("NURO", "检测到敏感内容，已进入眼瞎耳聋模式 🔒")

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
                self._popup.toast("NURO", "已进入眼瞎耳聋模式 🔒")
        else:
            self._set_character_state(FairyState.IDLE)
            if self._popup:
                self._popup.toast("NURO", "已退出眼瞎耳聋模式 👁️")

        # 重建菜单
        self._menu.delete(0, "end")
        self._create_menu()

    # ═══════════════════════════════════════════════════════
    #  悬浮模式
    # ═══════════════════════════════════════════════════════

    def _toggle_floating(self):
        """切换悬浮模式：隐藏主窗口，显示小圆点"""
        if self._floating:
            # 退出悬浮 → 恢复主窗口
            self._floating = False
            if self._float_dot:
                try:
                    self._float_dot.destroy()
                except Exception:
                    pass
                self._float_dot = None
            self.ball.deiconify()
            self.ball.attributes("-topmost", True)
            self._center_ball()
            self._apply_ball_acrylic()
            if self._popup:
                self._popup.toast("NURO", "已退出悬浮模式 📌")
        else:
            # 进入悬浮 → 隐藏主窗口，显示小圆点
            self._floating = True
            self.ball.withdraw()
            self._create_float_dot()
            if self._popup:
                self._popup.toast("NURO", "已进入悬浮模式，点击小圆点恢复")

    def _create_float_dot(self):
        """创建悬浮小幽灵（替代主窗口）"""
        dot_size = 48
        dot = tk.Toplevel(self.ball)
        dot.overrideredirect(True)
        dot.attributes("-topmost", True)
        dot.configure(bg=Palette.BG_DARK)
        bx = self.ball.winfo_x() + self.BALL_SIZE // 2 - dot_size // 2
        by = self.ball.winfo_y() + self.BALL_SIZE // 2 - dot_size // 2
        dot.geometry(f"{dot_size}x{dot_size}+{bx}+{by}")

        canvas = tk.Canvas(dot, width=dot_size, height=dot_size,
                           bg=Palette.BG_DARK, highlightthickness=0)
        canvas.pack()

        cx, cy = dot_size // 2, dot_size // 2 + 2
        r = 16

        # 紫色光晕
        canvas.create_oval(cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4,
                           fill="", outline=Palette.ACCENT, width=2)

        # 幽灵头部（白色圆角）
        canvas.create_oval(cx - r, cy - r + 4, cx + r, cy + r - 4,
                           fill="white", outline="", width=0)

        # 幽灵底部波浪
        wave_y = cy + r - 6
        for i, x_off in enumerate([-r, -r//2, 0, r//2, r]):
            wy = wave_y + (2 if i % 2 == 0 else -2)
            canvas.create_oval(cx + x_off - 4, wy - 4, cx + x_off + 4, wy + 4,
                               fill="white", outline="", width=0)

        # 左眼
        eye_r = 4
        le_x, le_y = cx - 6, cy - 3
        canvas.create_oval(le_x - eye_r, le_y - eye_r, le_x + eye_r, le_y + eye_r,
                           fill=Palette.BG_DARK, outline="")
        canvas.create_oval(le_x - eye_r + 1, le_y - eye_r + 1, le_x + eye_r - 2, le_y + eye_r - 2,
                           fill="white", outline="")

        # 右眼
        re_x, re_y = cx + 6, cy - 3
        canvas.create_oval(re_x - eye_r, re_y - eye_r, re_x + eye_r, re_y + eye_r,
                           fill=Palette.BG_DARK, outline="")
        canvas.create_oval(re_x - eye_r + 1, re_y - eye_r + 1, re_x + eye_r - 2, re_y + eye_r - 2,
                           fill="white", outline="")

        # 点击恢复
        canvas.bind("<Button-1>", lambda e: self._toggle_floating())
        canvas.bind("<Button-3>", self._show_float_menu)

        self._float_dot = dot
        self._float_dot._restore_cb = lambda e: self._toggle_floating()

    def _show_float_menu(self, event):
        """悬浮小圆点的右键菜单"""
        menu = tk.Menu(
            self._float_dot, tearoff=0,
            bg=Palette.BG_DARK, fg=Palette.TEXT_PRIMARY,
            activebackground=Palette.ACCENT, activeforeground="white",
            font=("Microsoft YaHei", 10),
        )
        menu.add_command(label="📌 恢复窗口", command=self._toggle_floating)
        menu.add_separator()
        menu.add_command(label="❌ 彻底退出", command=self._quit)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ═══════════════════════════════════════════════════════
    #  每日总结
    # ═══════════════════════════════════════════════════════

    def _schedule_daily_summary(self):
        """每天 22:00 自动生成总结

        BUG FIX: 原 daemon.py:1141 使用 timedelta(days=1) 但 timedelta 未导入。
        现通过 daily_summary.compute_next_summary_delay_ms() 计算延迟，
        该函数内部正确导入并使用 timedelta。
        """
        try:
            delay_ms = compute_next_summary_delay_ms()
            self.ball.after(delay_ms, self._auto_daily_summary)
        except Exception:
            pass

    def _auto_daily_summary(self):
        """自动触发每日总结"""
        if self._daily:
            def on_done(summary):
                if self._popup:
                    self._popup.toast("NURO 每日总结", "今天的锐评已生成，打开对话面板查看～")
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
            f"**NURO 桌面精灵 v{NURO_VERSION}**\n\n"
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
        if self._float_dot:
            try:
                self._float_dot.destroy()
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
