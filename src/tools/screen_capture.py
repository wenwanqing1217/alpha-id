"""
屏幕捕获工具 —— TwinBrain 的"眼睛"

提供截图能力：全屏、指定窗口、指定区域。
输出保存为临时图片文件，可喂给 LLM-vision 分析。
"""

import os
from datetime import datetime
from typing import Optional, Tuple

# 兼容本地运行：有 langchain 则用 @tool，没有则用空装饰器
try:
    from langchain.tools import tool  # pyright: ignore[reportMissingImports]
except ImportError:

    def tool(func=None, **kwargs):
        if func is not None:
            return func

        def decorator(f):
            return f

        return decorator

# ── 延迟导入，避免无依赖时报错 ──


def _import_pyautogui():
    """导入 pyautogui，失败时给清晰提示"""
    try:
        import pyautogui

        return pyautogui
    except ImportError:
        raise ImportError(
            "请安装 pyautogui：pip install pyautogui\n如果遇到依赖问题，可尝试：pip install pyautogui --upgrade"
        )


def _import_pil():
    """导入 PIL，失败时给清晰提示"""
    try:
        from PIL import Image

        return Image
    except ImportError:
        raise ImportError("请安装 Pillow：pip install Pillow")


def _import_pygetwindow():
    """导入 pygetwindow，失败时给清晰提示"""
    try:
        import pygetwindow as gw

        return gw
    except ImportError:
        raise ImportError("请安装 pygetwindow：pip install pygetwindow\nWindows 下用于按窗口标题查找和操作窗口。")


SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def _save_image(pil_image) -> str:
    """保存 PIL Image 到截图目录，返回文件路径"""
    _import_pil()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"screenshot_{timestamp}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    pil_image.save(filepath, "PNG")
    return os.path.abspath(filepath)


def _find_window_rect(title_pattern: str) -> Optional[Tuple[int, int, int, int]]:
    """
    按窗口标题模糊查找，返回 (left, top, width, height)。
    找不到返回 None。
    """
    gw = _import_pygetwindow()
    try:
        windows = gw.getWindowsWithTitle(title_pattern)
        # 过滤掉不可见窗口
        visible = [w for w in windows if w.visible]
        if not visible:
            # 退而求其次，只要不是最小化的
            visible = [w for w in windows if w.width > 0 and w.height > 0]
        if not visible:
            return None
        win = visible[0]
        if win.isMinimized:
            win.restore()
        return (win.left, win.top, win.width, win.height)
    except Exception:
        return None


@tool
def capture_full_screen() -> str:
    """
    截取全屏截图，保存到本地文件。

    返回文件路径，可传给 vision_tool 或直接给 LLM 分析。
    """
    pyautogui = _import_pyautogui()
    try:
        img = pyautogui.screenshot()
        path = _save_image(img)
        return f"✅ 全屏截图已保存: {path}"
    except Exception as e:
        return f"❌ 截图失败: {str(e)}"


@tool
def capture_application_window(window_title: str) -> str:
    """
    截取指定应用程序窗口的截图。

    参数:
        window_title: 窗口标题关键词（模糊匹配）。
                      例如 "BOSS直聘"、"拉勾"、"猎聘"、"WeChat"、"Chrome"。

    返回文件路径，可传给 vision_tool 或直接给 LLM 分析。
    """
    try:
        rect = _find_window_rect(window_title)
        if not rect:
            return (
                f"❌ 未找到标题包含「{window_title}」的窗口。\n"
                f"提示：先打开目标软件，再重试。可用 list_windows 查看当前所有窗口。"
            )

        left, top, width, height = rect
        pyautogui = _import_pyautogui()
        img = pyautogui.screenshot(region=(left, top, width, height))
        path = _save_image(img)
        return f"✅ 窗口「{window_title}」截图已保存: {path}\n   位置: ({left}, {top})  大小: {width}×{height}"
    except Exception as e:
        return f"❌ 窗口截图失败: {str(e)}"


@tool
def capture_region(x: int, y: int, width: int, height: int) -> str:
    """
    截取屏幕指定区域。

    参数:
        x: 左上角 X 坐标
        y: 左上角 Y 坐标
        width: 区域宽度
        height: 区域高度

    适用于：已知聊天区域位置后，精准截取消息列表。
    """
    pyautogui = _import_pyautogui()
    try:
        img = pyautogui.screenshot(region=(x, y, width, height))
        path = _save_image(img)
        return f"✅ 区域截图已保存: {path}\n   区域: ({x}, {y}, {width}×{height})"
    except Exception as e:
        return f"❌ 区域截图失败: {str(e)}"


@tool
def list_application_windows() -> str:
    """
    列出当前桌面上所有可见窗口的标题和位置。

    在截图前先用此命令找到目标窗口的准确标题。
    """
    gw = _import_pygetwindow()
    try:
        windows = gw.getAllWindows()
        visible = [w for w in windows if w.visible and w.title.strip()]
        if not visible:
            return "当前没有可见窗口。"

        lines = ["📋 当前可见窗口列表：", "─" * 60]
        for i, w in enumerate(visible, 1):
            lines.append(f"  {i}. [{w.title}]  位置({w.left}, {w.top})  大小({w.width}×{w.height})")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 获取窗口列表失败: {str(e)}"
