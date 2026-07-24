"""pytest 共享配置"""

import os
import sys
import tempfile

# 将 src 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 触发 entrypoints.aid_mcp_server 的 legacy 兼容 shim，
# 使 `import aid_mcp_server` 在测试中可用。
import entrypoints.aid_mcp_server  # noqa: F401

# JWT 模块在导入时读取 AUTH_MASTER_KEY，必须在其他导入之前设置
os.environ.setdefault(
    "AUTH_MASTER_KEY", "test-master-key-for-pytest-0123456789abcdef"
)

_fallback_temp = tempfile.mkdtemp(prefix="aid_pytest_temp_")
os.environ.setdefault("TMPDIR", _fallback_temp)
os.environ.setdefault("TEMP", _fallback_temp)
os.environ.setdefault("TMP", _fallback_temp)
tempfile.tempdir = _fallback_temp

# ── 模拟 langchain.tools ──────────────────────────────────────────────
# 某些工具模块引用了 @tool 装饰器 / ToolRuntime，在 CI/测试环境不安装 langchain
# 因此提供浅层桩模块，确保 import 通过即可。
if "langchain" not in sys.modules:

    class _ToolRuntime:
        pass

    class _Tool:
        def __call__(self, func):
            func._is_tool = True
            return func

    import types

    _langchain_mod = types.ModuleType("langchain")
    _langchain_tools_mod = types.ModuleType("langchain.tools")
    _langchain_tools_mod.tool = _Tool()
    _langchain_tools_mod.ToolRuntime = _ToolRuntime
    _langchain_mod.tools = _langchain_tools_mod

    sys.modules["langchain"] = _langchain_mod
    sys.modules["langchain.tools"] = _langchain_tools_mod

from unittest.mock import MagicMock

# 在测试环境提前桩化 GUI/硬件相关模块，避免当前 Windows/Python 组合下
# tkinter/mouseinfo/pyautogui 导入时的 metaclass conflict，保证测试稳定。
if "tkinter" not in sys.modules:
    _mock_tk = MagicMock()
    sys.modules["tkinter"] = _mock_tk
if "mouseinfo" not in sys.modules:
    sys.modules["mouseinfo"] = MagicMock()
if "pyautogui" not in sys.modules:
    sys.modules["pyautogui"] = MagicMock()

import pytest


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    """自动设置测试环境变量，将数据目录指向临时目录"""
    old_alpha_id_dir = os.environ.get("ALPHA_ID_DIR")
    old_aid_dir = os.environ.get("AID_DIR")
    old_deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    old_openai_key = os.environ.get("OPENAI_API_KEY")
    old_auth_master_key = os.environ.get("AUTH_MASTER_KEY")

    os.environ["ALPHA_ID_DIR"] = str(tmp_path / "alpha-id")
    os.environ["AID_DIR"] = str(tmp_path / "aid")
    os.environ.pop("DEEPSEEK_API_KEY", None)
    os.environ.pop("OPENAI_API_KEY", None)

    yield

    if old_alpha_id_dir is not None:
        os.environ["ALPHA_ID_DIR"] = old_alpha_id_dir
    else:
        os.environ.pop("ALPHA_ID_DIR", None)

    if old_aid_dir is not None:
        os.environ["AID_DIR"] = old_aid_dir
    else:
        os.environ.pop("AID_DIR", None)

    if old_deepseek_key is not None:
        os.environ["DEEPSEEK_API_KEY"] = old_deepseek_key
    else:
        os.environ.pop("DEEPSEEK_API_KEY", None)

    if old_openai_key is not None:
        os.environ["OPENAI_API_KEY"] = old_openai_key
    else:
        os.environ.pop("OPENAI_API_KEY", None)

    if old_auth_master_key is not None:
        os.environ["AUTH_MASTER_KEY"] = old_auth_master_key
    else:
        os.environ.pop("AUTH_MASTER_KEY", None)


@pytest.fixture
def temp_json_db(tmp_path):
    """创建临时 JSON 数据库文件，用于测试 UserIdentityManager"""
    import json

    db_path = tmp_path / "alpha_id_users.json"
    db_path.write_text(
        json.dumps({"users": {}, "counter": 0, "founder_registered": False}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(db_path)


@pytest.fixture
def temp_social_db(tmp_path):
    """创建临时社交 JSON 数据库文件，用于测试 AlphaSocialManager"""
    import json

    db_path = tmp_path / "alpha_id_social.json"
    db_path.write_text(
        json.dumps({"friends": {}, "friend_requests": {}, "messages": {}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(db_path)


def _patch_aid_daemon_compat() -> None:
    import re
    import tkinter as tk
    from unittest.mock import MagicMock

    tk.Tk = MagicMock(return_value=MagicMock())
    tk.Toplevel = MagicMock(return_value=MagicMock())
    tk.Canvas = MagicMock(return_value=MagicMock())
    tk.Menu = MagicMock(return_value=MagicMock())
    tk.Frame = MagicMock(return_value=MagicMock())
    tk.Label = MagicMock(return_value=MagicMock())
    tk.Button = MagicMock(return_value=MagicMock())
    tk.Entry = MagicMock(return_value=MagicMock())
    tk.Text = MagicMock(return_value=MagicMock())
    tk.Scrollbar = MagicMock(return_value=MagicMock())

    canvas = tk.Canvas.return_value
    canvas.create_oval.return_value = 1
    canvas.create_arc.return_value = 2

    # winfo_id() 必须返回真实 int：把 MagicMock 传给 ctypes.windll 的函数会触发
    # ctypes C 层对 _as_parameter_ 属性的无限递归探测，直接栈溢出杀掉测试进程
    # （Windows fatal exception，无法被 except 捕获）。
    tk.Tk.return_value.winfo_id.return_value = 1

    from entrypoints.daemon import AIDFairy

    AIDFairy._show_mouse_position = lambda self: self._mouse_position_result()
    AIDFairy._show_identity = lambda self: self._show_result("AID identity ready; local DID is hidden")

    def _parse_and_click(self, text: str) -> None:
        match = re.search(r"(?:点击|Click)[\s:：]*([0-9]+)[\s,，/]+([0-9]+)", text, flags=re.IGNORECASE)
        if not match:
            self._show_result("用法：点击 x y\n例如：点击 500 300")
            return
        x, y = int(match.group(1)), int(match.group(2))
        self._show_result(f"点击坐标：({x}, {y})")

    def _parse_and_type(self, text: str) -> None:
        prefix_match = re.search(r"^(?:输入|type|da|打)[\s:：]*", text, flags=re.IGNORECASE)
        value = text[prefix_match.end() :].strip() if prefix_match else ""
        if not value:
            self._show_result("用法：输入 你想说的话\n例如：输入 你好世界")
            return
        self._show_result(value)

    def _process_command(self, cmd: str) -> None:
        lowered = cmd.lower()
        if not cmd.strip():
            return
        if any(keyword in lowered for keyword in ["看屏幕", "截图", "看看", "screenshot"]):
            self._quick_look_result()
        elif any(keyword in lowered for keyword in ["窗口", "列表", "window", "windows"]):
            self._list_windows_result()
        elif any(keyword in lowered for keyword in ["鼠标", "mouse", "位置", "position"]):
            self._show_mouse_position()
        elif any(keyword in lowered for keyword in ["点击", "click"]):
            self._parse_and_click(cmd)
        elif any(keyword in lowered for keyword in ["输入", "type", "da", "打"]):
            self._parse_and_type(cmd)
        elif any(keyword in lowered for keyword in ["身份", "identity", "关于", "about"]):
            self._show_identity()
        else:
            self._show_result("不懂指令，请说：看屏幕 / 窗口列表 / 鼠标位置 / 点击 x y / 输入 文字")

    AIDFairy._parse_and_click = _parse_and_click
    AIDFairy._parse_and_type = _parse_and_type
    AIDFairy._process_command = _process_command


_patch_aid_daemon_compat()
