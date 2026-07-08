"""Legacy compatibility shim for aid_daemon imports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from entrypoints import daemon as _daemon_module
from entrypoints.daemon import AIDFairy

sys.modules.setdefault("aid_daemon", sys.modules[__name__])

AIDFairy._show_mouse_position = lambda self: self._mouse_position_result()
AIDFairy._show_identity = lambda self: self._show_result("AID identity ready; local DID is hidden")


def _parse_and_click(self, text: str) -> None:
    import re

    match = re.search(r"(?:点击|Click)[\s:：]*([0-9]+)[\s,，/]+([0-9]+)", text, flags=re.IGNORECASE)
    if not match:
        self._show_result("用法：点击 x y\n例如：点击 500 300")
        return
    x, y = int(match.group(1)), int(match.group(2))
    self._show_result(f"点击坐标：({x}, {y})")


def _parse_and_type(self, text: str) -> None:
    import re

    prefix_match = re.search(r"^(?:输入|type|da|打)[\s:：]*", text, flags=re.IGNORECASE)
    value = text[prefix_match.end():].strip() if prefix_match else ""
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
