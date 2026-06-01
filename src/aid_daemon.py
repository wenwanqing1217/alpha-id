"""
AID Daemon — 桌面精灵
淡粉色悬浮球，常驻桌面。双击指令 / 右键菜单 / 语音输入。

用法：
    python src/aid_daemon.py
"""

import os
import subprocess
import sys
import argparse
import threading
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 版本 ──

try:
    from alpha_id import __version__

    VERSION = __version__
except ImportError:
    VERSION = "0.1.0"

# ── LLM 大脑 ──

HAS_LLM = False
HAS_MEMORY = False
try:
    from core.memory_store import MemoryStore
    from core.storage_sqlite import SqliteStorage
    from fairy_agent import FairyBrain

    HAS_LLM = bool(os.getenv("OPENAI_API_KEY", ""))
    HAS_MEMORY = True
except ImportError:
    pass

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
        click_on_screen,
        get_mouse_position,
        list_application_windows,
        type_text,
    )

    HAS_WINDOW = True
except ImportError as e:
    _cap_err["窗口控制"] = str(e)

# ── 语音合成（TTS） ──
HAS_TTS = False
try:
    import win32com.client

    _tts_engine = win32com.client.Dispatch("SAPI.SpVoice")
    # 选择中文语音
    voices = _tts_engine.GetVoices()
    for i in range(voices.Count):
        desc = voices.Item(i).GetDescription()
        if "Chinese" in desc or "中文" in desc:
            _tts_engine.Voice = voices.Item(i)
            break
    HAS_TTS = True
except Exception:
    pass

# ── 语音识别（STT） ──
HAS_SPEECH_RECOGNITION = False
try:
    import speech_recognition as sr  # noqa: F401
    import sounddevice  # noqa: F401

    HAS_SPEECH_RECOGNITION = True
except ImportError:
    pass
HAS_SPEECH = HAS_SPEECH_RECOGNITION  # 向后兼容

# ── Tkinter ──
try:
    import tkinter as tk
except ImportError:
    sys.exit("tkinter 不可用。请安装 Python 时勾选 'tcl/tk and IDLE'。")


# ══════════════════════════════════════════════════════════
#  AID 桌面精灵
# ══════════════════════════════════════════════════════════


class AIDFairy:
    """AID 桌面精灵 — 暗色磨砂玻璃悬浮球。双击输入 / 右键菜单 / 语音指令。"""

    # ── 调色板（暗色磨砂玻璃风） ──
    BG_DARK = "#1A1A2E"  # 深空底色
    BG_FROST = "#252540"  # 磨砂玻璃层
    BG_LIGHT = "#2E2E4A"  # 浅层
    ACCENT = "#7C6FFF"  # 紫罗兰主色
    ACCENT_DIM = "#5A4FBF"  # 暗紫
    ACCENT_GLOW = "#9D8FFF"  # 亮紫辉光
    TEXT_PRIMARY = "#EEEEFF"  # 主文字
    TEXT_SECONDARY = "#8888BB"  # 次级文字
    TEXT_DIM = "#555577"  # 弱文字
    BORDER = "#3A3A5E"  # 边框
    SUCCESS = "#44DDBB"  # 成功绿

    BALL_SIZE = 48  # 悬浮球直径（小巧精致）
    MCP_PORT = 8001

    def __init__(self, no_mcp=False, no_brain=False, debug=False):
        self.root = tk.Tk()
        self.root.title("AID")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#FFFFFF")
        self.root.configure(bg="#FFFFFF")

        self._no_brain = no_brain
        self._no_mcp = no_mcp
        self._debug = debug

        self._center_window()
        self.root.wm_attributes("-alpha", 0.90)

        # 拖拽状态
        self._drag_x = 0
        self._drag_y = 0
        self._is_dragging = False

        # MCP 子进程
        self._mcp_process: Optional[subprocess.Popen] = None

        # LLM 大脑 + 记忆
        self._brain: Optional["FairyBrain"] = None
        self._memory_store: Optional["MemoryStore"] = None
        self._init_brain()

        # 对话框引用（防止被 GC）
        self._dialog_win: Optional[tk.Toplevel] = None
        self._result_win: Optional[tk.Toplevel] = None

        # 创建 UI
        self._create_ball()
        self._create_menu()

        # 启动 MCP 后台
        if not self._no_mcp:
            self._start_mcp_server()

    def _center_window(self):
        """初始位置：屏幕右上角"""
        s = self.BALL_SIZE
        self.root.geometry(f"{s}x{s}+0+0")
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        x = sw - s - 30
        y = 100
        self.root.geometry(f"{s}x{s}+{x}+{y}")

    # ═══════════════════════════════════════════════════════
    #  悬浮球绘制
    # ═══════════════════════════════════════════════════════

    def _create_ball(self):
        """绘制极简悬浮球 — 磨砂玻璃质感 + 状态光晕"""
        s = self.BALL_SIZE
        c = tk.Canvas(
            self.root,
            width=s,
            height=s,
            bg="#FFFFFF",
            highlightthickness=0,
        )
        c.pack()

        m = 3  # margin

        # 1. 外圈光晕（投影效果）
        c.create_oval(
            m + 2,
            m + 2,
            s - m + 2,
            s - m + 2,
            fill="",
            outline="#222222",
            width=2,
        )

        # 2. 主圆 — 暗色渐变底
        c.create_oval(
            m,
            m,
            s - m,
            s - m,
            fill=self.BG_FROST,
            outline=self.BORDER,
            width=1.5,
        )

        # 3. 内发光弧（左上高光）
        c.create_arc(
            m + 4,
            m + 4,
            s - m - 4,
            s - m - 4,
            start=-45,
            extent=160,
            fill="",
            outline="#FFFFFF",
            width=1,
            style="arc",
        )

        # 4. 底部弧光
        c.create_arc(
            m + 8,
            m + 8,
            s - m - 8,
            s - m - 8,
            start=135,
            extent=110,
            fill="",
            outline="#FFFFFF",
            width=1,
            style="arc",
        )

        # 5. 中心小圆点 — 状态指示器
        self._state_dot = c.create_oval(
            s // 2 - 3,
            s // 2 - 3,
            s // 2 + 3,
            s // 2 + 3,
            fill="#555577",
            outline="",
        )

        # 事件绑定
        self._circle_tag = "main"
        c.tag_bind("all", "<Button-1>", self._start_drag)
        c.tag_bind("all", "<B1-Motion>", self._on_drag)
        c.tag_bind("all", "<ButtonRelease-1>", self._end_drag)
        c.tag_bind("all", "<Double-Button-1>", self._on_double_click)
        c.tag_bind("all", "<Button-3>", self._show_menu)
        c.tag_bind("all", "<Enter>", self._on_hover)
        c.tag_bind("all", "<Leave>", self._on_leave)

        self._canvas = c

    def _on_hover(self, event=None):
        """悬浮变亮"""
        self.root.wm_attributes("-alpha", 1.0)

    def _on_leave(self, event=None):
        """离开恢复"""
        self.root.wm_attributes("-alpha", 0.90)

    # ── 拖拽 ──

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()
        self._is_dragging = False

    def _on_drag(self, event):
        dx = abs(event.x_root - self.root.winfo_x() - self._drag_x)
        dy = abs(event.y_root - self.root.winfo_y() - self._drag_y)
        if dx > 3 or dy > 3:
            self._is_dragging = True
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _end_drag(self, event):
        pass

    # ── 右键菜单 ──

    def _create_menu(self):
        self._menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=self.BG_DARK,
            fg=self.TEXT_PRIMARY,
            activebackground=self.ACCENT,
            activeforeground="white",
            font=("Microsoft YaHei", 10),
        )
        self._menu.add_command(label="看屏幕", command=self._quick_look)
        if HAS_SPEECH_RECOGNITION:
            self._menu.add_command(label="语音指令", command=self._voice_command)
        self._menu.add_separator()
        self._menu.add_command(label="身份信息", command=self._show_identity)
        self._menu.add_command(label="关于 AID", command=self._show_about)
        self._menu.add_separator()
        self._menu.add_command(label="退出", command=self._quit)

    def _show_menu(self, event):
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    # ── 双击：命令输入（不再阻塞主窗口） ──

    def _init_brain(self):
        """初始化 LLM 大脑 + 记忆持久化"""
        if self._no_brain:
            return
        if not HAS_MEMORY:
            return
        try:
            # 使用 SQLite 持久化存储
            db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "fairy_memory.db")
            storage = SqliteStorage(db_path)
            self._memory_store = MemoryStore(alpha_id="desktop_fairy", storage=storage)
        except Exception as e:
            print(f"  [AID] Memory init: {e}")
            self._memory_store = None

        try:
            if HAS_LLM:
                self._brain = FairyBrain(fairy=self, memory_store=self._memory_store)
                if self._brain.available:
                    print(f"  Brain:  ✅ LLM ({self._brain.model})")
                else:
                    print("  Brain:  ⏳ 已加载（需设置 OPENAI_API_KEY 启用 LLM）")
                    self._brain = None
            else:
                print("  Brain:  ⏳ 已加载（需设置 OPENAI_API_KEY + pip install openai）")
        except Exception as e:
            print(f"  [AID] Brain init: {e}")
            self._brain = None

    def _on_double_click(self, event):
        if self._is_dragging:
            return
        self._show_command_dialog()

    def _show_command_dialog(self):
        """打开指令输入框 — 非阻塞"""
        # 如果已打开则聚焦
        if self._dialog_win and self._dialog_win.winfo_exists():
            self._dialog_win.lift()
            self._dialog_win.focus_set()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("AID 指令")
        dialog.configure(bg=self.BG_DARK)
        dialog.overrideredirect(True)
        dialog.attributes("-topmost", True)
        dialog.transient(self.root)

        w, h = 360, 160
        x = self.root.winfo_x() - 90
        y = self.root.winfo_y() + self.BALL_SIZE + 8
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        # 外边框（用 Frame 模拟圆角）
        outer = tk.Frame(dialog, bg=self.BORDER, bd=1)
        outer.pack(fill="both", expand=True, padx=0, pady=0)

        # 标题栏
        title_bar = tk.Frame(outer, bg=self.BG_DARK, height=24)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        tk.Label(
            title_bar,
            text="  AID",
            bg=self.BG_DARK,
            fg=self.ACCENT_GLOW,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        tk.Button(
            title_bar,
            text="✕",
            bg=self.BG_DARK,
            fg=self.TEXT_DIM,
            bd=0,
            font=("Segoe UI", 9),
            command=dialog.destroy,
            activebackground=self.BG_LIGHT,
            activeforeground=self.TEXT_PRIMARY,
        ).pack(side="right", padx=4)

        # 内容区
        content = tk.Frame(outer, bg=self.BG_DARK, padx=10, pady=6)
        content.pack(fill="both", expand=True)

        tk.Label(
            content,
            text="你想让我做什么？",
            bg=self.BG_DARK,
            fg=self.TEXT_SECONDARY,
            font=("Microsoft YaHei", 9),
        ).pack(anchor="w")

        entry_frame = tk.Frame(
            content,
            bg=self.BG_FROST,
            bd=0,
            highlightthickness=1,
            highlightcolor=self.ACCENT,
            highlightbackground=self.BORDER,
        )
        entry_frame.pack(fill="x", pady=(4, 8))

        entry = tk.Entry(
            entry_frame,
            font=("Microsoft YaHei", 11),
            bd=0,
            bg=self.BG_FROST,
            fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY,
            relief="flat",
        )
        entry.pack(fill="x", padx=8, pady=6)
        entry.focus_set()

        # 按钮行
        btn_frame = tk.Frame(content, bg=self.BG_DARK)
        btn_frame.pack(fill="x")

        def _quick_cmd(text):
            entry.delete(0, "end")
            entry.insert(0, text)
            dialog.destroy()
            self._dialog_win = None
            self._process_command(text)

        # 快捷按钮
        style = dict(
            bg=self.ACCENT,
            fg="white",
            bd=0,
            padx=8,
            pady=2,
            font=("Microsoft YaHei", 9),
            cursor="hand2",
            activebackground=self.ACCENT_DIM,
        )
        tk.Button(
            btn_frame,
            text="看屏幕",
            **style,
            command=lambda: _quick_cmd("看屏幕"),
        ).pack(side="left", padx=2)
        tk.Button(
            btn_frame,
            text="窗口列表",
            **style,
            command=lambda: _quick_cmd("当前窗口"),
        ).pack(side="left", padx=2)
        tk.Button(
            btn_frame,
            text="鼠标位置",
            **style,
            command=lambda: _quick_cmd("鼠标位置"),
        ).pack(side="left", padx=2)

        # 语音按钮（右侧）
        if HAS_SPEECH:
            mic_style = dict(
                bg=self.BG_FROST,
                fg=self.TEXT_PRIMARY,
                bd=0,
                padx=8,
                pady=2,
                font=("Segoe UI", 9),
                cursor="hand2",
                activebackground=self.BG_LIGHT,
            )
            tk.Button(
                btn_frame,
                text="🎤 语音",
                **mic_style,
                command=lambda: self._voice_command(dialog, entry),
            ).pack(side="right", padx=2)

        # 回车执行
        def _on_enter(e):
            cmd = entry.get().strip()
            if cmd:
                dialog.destroy()
                self._dialog_win = None
                self._process_command(cmd)

        entry.bind("<Return>", _on_enter)

        # 拖拽标题栏
        def _sm(e):
            dialog._mx, dialog._my = e.x_root - dialog.winfo_x(), e.y_root - dialog.winfo_y()

        def _dm(e):
            dialog.geometry(f"+{e.x_root - dialog._mx}+{e.y_root - dialog._my}")

        title_bar.bind("<Button-1>", _sm)
        title_bar.bind("<B1-Motion>", _dm)

        # 关闭时清理引用
        def _on_close():
            dialog.destroy()
            self._dialog_win = None

        dialog.protocol("WM_DELETE_WINDOW", _on_close)

        # 焦点 — 不用 grab_set()，避免阻塞主窗口交互
        dialog.focus_force()
        entry.focus_set()

        self._dialog_win = dialog

    # ── 语音输入 ──

    def _voice_command(self, dialog_win=None, entry_widget=None):
        """语音输入 — 使用 SpeechRecognition (Google STT)"""
        if not HAS_SPEECH_RECOGNITION:
            self._show_result(
                "🎤 语音识别未安装\npip install SpeechRecognition sounddevice"
            )
            return

        self._show_result("🎤 聆听中...")

        def _do():
            try:
                import speech_recognition as sr

                r = sr.Recognizer()
                with sr.Microphone() as source:
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    audio = r.listen(source, timeout=5, phrase_time_limit=10)

                text = r.recognize_google(audio, language="zh-CN")
                if dialog_win and dialog_win.winfo_exists() and entry_widget:
                    entry_widget.delete(0, "end")
                    entry_widget.insert(0, text)
                    dialog_win.destroy()
                    self._dialog_win = None
                    self._process_command(text)
                else:
                    self._process_command(text)
            except sr.WaitTimeoutError:
                self._show_result("🎤 没听到声音")
            except sr.UnknownValueError:
                self._show_result("🎤 没听清，请再说一次")
            except Exception as e:
                self._show_result(f"🎤 语音识别出错：{e}")

        threading.Thread(target=_do, daemon=True).start()

    # ── 命令处理 ──

    def _process_command(self, cmd: str):
        cmd = cmd.strip()
        if not cmd:
            return

        # ── 优先走 LLM 大脑 ──
        if self._brain and self._brain.available:
            result = self._brain.process(cmd)
            if result:
                return  # FairyBrain 会异步调用 _show_result

        # ── 降级：关键词匹配 ──
        cmd_lower = cmd.lower()

        if any(kw in cmd_lower for kw in ["看屏幕", "截图", "看看", "截屏", "screenshot"]):
            self._quick_look()
        elif any(kw in cmd_lower for kw in ["窗口", "列表", "当前窗口", "windows"]):
            self._list_windows()
        elif any(kw in cmd_lower for kw in ["鼠标", "mouse", "位置"]):
            self._show_mouse_position()
        elif any(kw in cmd_lower for kw in ["点", "click", "点击"]):
            self._parse_and_click(cmd)
        elif any(kw in cmd_lower for kw in ["打", "输", "type", "输入", "写"]):
            self._parse_and_type(cmd)
        elif any(kw in cmd_lower for kw in ["身份", "did", "identity"]):
            self._show_identity()
        else:
            self._show_result(f"不懂指令: {cmd}\n试试: 看屏幕 / 窗口列表 / 鼠标位置 / 点击...")

    def _quick_look(self):
        if not HAS_SCREEN:
            self._show_result("截图工具不可用")
            return

        self._show_result("正在看屏幕...")

        def _do():
            try:
                img_path = capture_full_screen()
                if not img_path or not os.path.exists(img_path):
                    self._show_result("截图失败")
                    return

                if HAS_OCR:
                    text = ocr_text(img_path, lang="chi_sim+eng")
                    if text:
                        preview = text[:500]
                        if len(text) > 500:
                            preview += "..."
                        self._show_result(f"屏幕上看到：\n{preview}")
                    else:
                        self._show_result(f"截图已保存：{img_path}\n（未识别到文字）")
                else:
                    self._show_result(f"截图已保存：{img_path}")
            except Exception as e:
                self._show_result(f"看屏幕失败：{e}")

        threading.Thread(target=_do, daemon=True).start()

    def _list_windows(self):
        if not HAS_WINDOW:
            self._show_result("窗口控制不可用")
            return
        try:
            windows = list_application_windows()
            self._show_result(f"当前窗口：\n{windows[:1000]}")
        except Exception as e:
            self._show_result(f"获取窗口列表失败：{e}")

    def _show_mouse_position(self):
        if not HAS_WINDOW:
            self._show_result("窗口控制不可用")
            return
        try:
            pos = get_mouse_position()
            self._show_result(f"鼠标位置：{pos}")
        except Exception as e:
            self._show_result(f"获取鼠标位置失败：{e}")

    def _parse_and_click(self, cmd: str):
        import re

        nums = re.findall(r"\d+", cmd)
        if len(nums) >= 2:
            x, y = int(nums[0]), int(nums[1])
            if not HAS_WINDOW:
                self._show_result("窗口控制不可用")
                return
            try:
                result = click_on_screen(x, y)
                self._show_result(f"点击 ({x}, {y})\n{result}")
            except Exception as e:
                self._show_result(f"点击失败：{e}")
        else:
            self._show_result("用法：点击 x y\n例如：点击 500 300")

    def _parse_and_type(self, cmd: str):
        for prefix in ["打", "输", "输入", "写", "type"]:
            if cmd.startswith(prefix):
                text = cmd[len(prefix) :].strip()
                if text:
                    if not HAS_WINDOW:
                        self._show_result("窗口控制不可用")
                        return
                    try:
                        type_text(text)
                        self._show_result(f"已输入：{text}")
                    except Exception as e:
                        self._show_result(f"输入失败：{e}")
                    return
        self._show_result("用法：输入 你想说的话\n例如：输入 你好世界")

    # ── 语音回话（TTS） ──

    def _speak(self, text: str):
        """用中文语音读出文本（非阻塞后台线程）"""
        if not HAS_TTS:
            return
        # 清理：去掉 emoji、标点符号后的非中文内容保留
        import re

        clean = re.sub(r"[🌐🎤🎧🔊📸✅❌➕⭐📋🖥️⬆️⏎🔄📍]", "", text)
        # 太长的只读前半段
        if len(clean) > 120:
            clean = clean[:120]

        def _do():
            try:
                _tts_engine.Speak(clean)
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()

    # ── 结果展示（美化） ──

    def _show_result(self, text: str):
        self.root.after(0, self._show_result_ui, text)
        self._speak(text)  # 同时用语音读出来

    def _show_result_ui(self, text: str):
        if hasattr(self, "_result_win") and self._result_win and self._result_win.winfo_exists():
            self._result_win.destroy()

        win = tk.Toplevel(self.root)
        win.title("AID 回复")
        win.configure(bg=self.BG_DARK)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.transient(self.root)

        lines = text.count("\n") + 1
        longest = len(max(text.split("\n"), key=len))
        w = min(420, max(260, longest * 8 + 40))
        h = min(400, max(70, lines * 18 + 50))

        x = self.root.winfo_x() - 120
        y = self.root.winfo_y() + self.BALL_SIZE + 8
        win.geometry(f"{w}x{h}+{x}+{y}")

        # 外边框
        outer = tk.Frame(win, bg=self.BORDER, bd=1)
        outer.pack(fill="both", expand=True)

        # 标题栏
        title_bar = tk.Frame(outer, bg=self.BG_DARK, height=22)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        tk.Label(
            title_bar,
            text="  AID",
            bg=self.BG_DARK,
            fg=self.ACCENT_GLOW,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        # 关闭按钮
        tk.Button(
            title_bar,
            text="✕",
            bg=self.BG_DARK,
            fg=self.TEXT_DIM,
            bd=0,
            font=("Segoe UI", 9),
            activebackground=self.BG_LIGHT,
            activeforeground=self.TEXT_PRIMARY,
            command=win.destroy,
        ).pack(side="right", padx=4)

        # 内容（暗色背景，白色文字）
        text_frame = tk.Frame(outer, bg=self.BG_DARK)
        text_frame.pack(fill="both", expand=True, padx=8, pady=6)

        text_widget = tk.Text(
            text_frame,
            wrap="word",
            font=("Microsoft YaHei", 10),
            bg=self.BG_FROST,
            fg=self.TEXT_PRIMARY,
            bd=0,
            relief="flat",
            padx=10,
            pady=8,
            height=min(15, lines + 2),
            insertbackground=self.TEXT_PRIMARY,
        )
        text_widget.insert("1.0", text)
        text_widget.configure(state="disabled")
        text_widget.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(
            text_frame,
            command=text_widget.yview,
            bg=self.BG_DARK,
            troughcolor=self.BG_DARK,
            activebackground=self.ACCENT,
        )
        scrollbar.pack(side="right", fill="y")
        text_widget.configure(yscrollcommand=scrollbar.set)

        # 关闭按钮
        btn_frame = tk.Frame(outer, bg=self.BG_DARK)
        btn_frame.pack(fill="x", padx=8, pady=(0, 6))
        tk.Button(
            btn_frame,
            text="关闭",
            bg=self.ACCENT,
            fg="white",
            bd=0,
            padx=12,
            font=("Microsoft YaHei", 9),
            activebackground=self.ACCENT_DIM,
            command=win.destroy,
        ).pack(side="right")

        # 15 秒自动关
        win.after(15000, lambda: win.destroy() if win.winfo_exists() else None)

        self._result_win = win

    # ── 信息展示 ──

    def _show_identity(self):
        from alpha_id import AIDSigner

        signer = AIDSigner()
        try:
            signer.load_from_aid_dir()
            did = signer.did
            pk = signer.public_key.hex()[:16] + "..."
            self._show_result(f"AID 身份\n\nDID: {did}\n公钥: {pk}")
        except Exception:
            self._show_result("尚未初始化 AID 身份\n\n命令行初始化：aid identity init")

    def _show_about(self):
        info = (
            "AID 桌面精灵 v0.1\n\n"
            "你桌面上的深色磨砂玻璃球。\n"
            "双击 → 输入指令\n"
            "右键 → 快捷菜单\n"
            "🎤 语音输入\n\n"
            "能力：截图 / OCR / 窗口控制"
        )
        if not HAS_SCREEN:
            info += "\n截图工具未安装"
        if not HAS_OCR:
            info += "\nOCR 工具未安装"
        if not HAS_WINDOW:
            info += "\n窗口控制未安装"
        self._show_result(info)

    # ── MCP 后台 ──

    def _start_mcp_server(self):
        def _run():
            try:
                script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aid_mcp_server.py")
                self._mcp_process = subprocess.Popen(
                    [sys.executable, script, "--transport", "sse", "--port", str(self.MCP_PORT)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    # ── 退出 ──

    def _quit(self):
        if self._mcp_process:
            try:
                self._mcp_process.terminate()
                self._mcp_process.wait(timeout=3)
            except Exception:
                pass
        self.root.destroy()

    # ── 运行 ──

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self._quit()


# ══════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="AID 桌面精灵 — 深色磨砂玻璃悬浮球，常驻桌面"
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"AID Desktop Fairy v{VERSION}",
    )
    parser.add_argument(
        "--no-mcp", action="store_true", help="不启动 MCP 后台服务器"
    )
    parser.add_argument(
        "--no-brain", action="store_true", help="不加载 LLM 大脑"
    )
    parser.add_argument(
        "--debug", action="store_true", help="输出调试日志"
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("[AID] Desktop Fairy starting...")
    print(f"  Screen:    {'✅' if HAS_SCREEN else '❌'}")
    print(f"  OCR:       {'✅' if HAS_OCR else '❌'}")
    print(f"  Window:    {'✅' if HAS_WINDOW else '❌'}")
    print(f"  Voice:     {'✅' if HAS_SPEECH else '❌'}")
    print(f"  Memory:    {'✅' if HAS_MEMORY else '❌'}")
    print(f"  Brain:     {'✅' if HAS_LLM else '⏳ (需 OPENAI_API_KEY)'}")
    if not HAS_SCREEN:
        print("  TIP: pip install pyautogui pygetwindow Pillow")
    if not HAS_OCR:
        print("  TIP: pip install pytesseract Pillow")
    print()
    print("  Double-click -> command input")
    print("  Right-click  -> quick menu")
    print("  Drag         -> reposition")
    print()

    fairy = AIDFairy(no_mcp=args.no_mcp, no_brain=args.no_brain, debug=args.debug)
    fairy.run()


if __name__ == "__main__":
    main()
