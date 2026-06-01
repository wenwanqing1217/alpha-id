"""
窗口控制工具 —— TwinBrain 的"手"

提供鼠标点击、键盘输入、窗口管理能力。
与 screen_capture 配合，构成完整的"看+点"闭环。
"""

import time
from typing import Optional

# 兼容本地运行：有 langchain 则用 @tool，没有则用空装饰器
try:
    from langchain.tools import tool
except ImportError:

    def tool(func=None, **kwargs):
        if func is not None:
            return func

        def decorator(f):
            return f

        return decorator


def _import_pyautogui():
    try:
        import pyautogui

        pyautogui.FAILSAFE = True  # 鼠标移到左上角可紧急停止
        pyautogui.PAUSE = 0.3  # 每个操作间隔，模拟人类操作节奏
        return pyautogui
    except ImportError:
        raise ImportError("请安装 pyautogui：pip install pyautogui")


def _import_pygetwindow():
    try:
        import pygetwindow as gw

        return gw
    except ImportError:
        raise ImportError("请安装 pygetwindow：pip install pygetwindow")


# ── 工具函数 ──


def _find_and_focus(title_pattern: str) -> Optional[dict]:
    """查找窗口并激活，返回窗口信息或 None"""
    gw = _import_pygetwindow()
    try:
        windows = gw.getWindowsWithTitle(title_pattern)
        visible = [w for w in windows if w.visible and w.title.strip()]
        if not visible:
            visible = [w for w in windows if w.width > 0 and w.height > 0]
        if not visible:
            return None

        win = visible[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        time.sleep(0.5)  # 等窗口激活
        return {
            "title": win.title,
            "left": win.left,
            "top": win.top,
            "width": win.width,
            "height": win.height,
        }
    except Exception:
        return None


# ── 工具 ──


@tool
def focus_application_window(window_title: str) -> str:
    """
    激活指定应用程序窗口，将其带到前台。

    参数:
        window_title: 窗口标题关键词（模糊匹配）

    在点击/输入之前，先确保窗口在前台。
    """
    info = _find_and_focus(window_title)
    if not info:
        return f"❌ 未找到标题包含「{window_title}」的窗口。\n先用 list_application_windows 查看当前窗口列表。"
    return (
        f"✅ 已激活窗口: {info['title']}\n"
        f"   位置: ({info['left']}, {info['top']})  "
        f"大小: {info['width']}×{info['height']}"
    )


@tool
def click_on_screen(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """
    在屏幕指定坐标处点击。

    参数:
        x: X 坐标
        y: Y 坐标
        button: 鼠标按键 (left/right/middle)
        clicks: 点击次数 (1=单击, 2=双击)

    坐标来自截图分析或窗口定位信息。
    """
    pyautogui = _import_pyautogui()
    try:
        # 先移动过去，再点击（更像人类操作）
        pyautogui.moveTo(x, y, duration=0.2)
        time.sleep(0.1)
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return f"✅ 已点击 ({x}, {y}) {button}键 {clicks}次"
    except Exception as e:
        return f"❌ 点击失败: {str(e)}"


@tool
def double_click_on_screen(x: int, y: int) -> str:
    """在屏幕指定坐标处双击。"""
    return click_on_screen(x=x, y=y, button="left", clicks=2)


@tool
def right_click_on_screen(x: int, y: int) -> str:
    """在屏幕指定坐标处右键。"""
    return click_on_screen(x=x, y=y, button="right", clicks=1)


@tool
def type_text(text: str, interval: float = 0.05) -> str:
    """
    在当前聚焦位置输入文本。

    参数:
        text: 要输入的文本内容（支持中文）
        interval: 每次按键间隔（秒），默认 0.05，模拟人类打字节奏

    先确保目标输入框已聚焦（用 click_on_screen 点一下输入框）。

    注意：
    - 中文输入法下可能有问题，建议先切换到英文输入法
    - 复杂场景可用 type_at_position 代替
    """
    pyautogui = _import_pyautogui()
    try:
        # 先快捷键清空可能的选择状态
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("backspace")
        time.sleep(0.1)
        # 打字
        pyautogui.write(text, interval=interval)
        return f"✅ 已输入 {len(text)} 个字符"
    except Exception as e:
        return f"❌ 输入失败: {str(e)}"


@tool
def type_at_position(text: str, x: int, y: int, interval: float = 0.05) -> str:
    """
    在屏幕指定坐标点击并输入文本。

    参数:
        text: 要输入的文本
        x: 输入框的 X 坐标
        y: 输入框的 Y 坐标
        interval: 按键间隔（秒）

    常用场景：分析完截图后，知道了消息输入框的位置，直接点进去打字。
    """
    click_result = click_on_screen(x=x, y=y, button="left", clicks=1)
    if "❌" in click_result:
        return click_result
    time.sleep(0.3)
    return type_text(text=text, interval=interval)


@tool
def press_key(keys: str) -> str:
    """
    按下键盘快捷键。

    参数:
        keys: 按键组合，用 + 连接。
              例如: "enter", "ctrl+v", "alt+tab", "ctrl+shift+z"

    常用快捷键：
    - 发送消息: enter
    - 粘贴: ctrl+v
    - 复制: ctrl+c
    - 截全屏: alt+prtsc
    - 切换窗口: alt+tab
    """
    pyautogui = _import_pyautogui()
    try:
        key_list = [k.strip().lower() for k in keys.split("+")]
        if len(key_list) == 1:
            pyautogui.press(key_list[0])
        else:
            pyautogui.hotkey(*key_list)
        return f"✅ 已按下快捷键: {keys}"
    except Exception as e:
        return f"❌ 按键失败: {str(e)}"


@tool
def press_enter() -> str:
    """按下回车键（常用于发送消息或确认）。"""
    return press_key("enter")


@tool
def scroll_mouse(clicks: int = -3, x: Optional[int] = None, y: Optional[int] = None) -> str:
    """
    滚动鼠标滚轮。

    参数:
        clicks: 滚动格数，正数=向上，负数=向下。默认 -3（向下滚3格）
        x: 滚动位置的 X 坐标（可选，不指定则在当前位置）
        y: 滚动位置的 Y 坐标（可选）

    用于滚动聊天记录或消息列表。
    """
    pyautogui = _import_pyautogui()
    try:
        if x is not None and y is not None:
            pyautogui.moveTo(x, y, duration=0.2)
            time.sleep(0.1)
        pyautogui.scroll(clicks)
        direction = "向上" if clicks > 0 else "向下"
        return f"✅ 已滚动 {direction} {abs(clicks)} 格"
    except Exception as e:
        return f"❌ 滚动失败: {str(e)}"


@tool
def drag_mouse(from_x: int, from_y: int, to_x: int, to_y: int, duration: float = 0.5) -> str:
    """
    从起点拖动鼠标到终点。

    参数:
        from_x: 起点 X
        from_y: 起点 Y
        to_x: 终点 X
        to_y: 终点 Y
        duration: 拖动持续秒数

    用于滑动列表、拖动滑块等。
    """
    pyautogui = _import_pyautogui()
    try:
        pyautogui.moveTo(from_x, from_y, duration=0.2)
        time.sleep(0.1)
        pyautogui.drag(to_x, to_y, button="left", duration=duration)
        return f"✅ 已从 ({from_x}, {from_y}) 拖动到 ({to_x}, {to_y})"
    except Exception as e:
        return f"❌ 拖动失败: {str(e)}"


@tool
def get_mouse_position() -> str:
    """
    获取当前鼠标位置。

    用于定位坐标：先把鼠标放到目标位置，然后运行此命令获取坐标。
    """
    pyautogui = _import_pyautogui()
    try:
        x, y = pyautogui.position()
        screen_width, screen_height = pyautogui.size()
        return f"🖱 当前鼠标位置: ({x}, {y})\n   屏幕分辨率: {screen_width}×{screen_height}"
    except Exception as e:
        return f"❌ 获取鼠标位置失败: {str(e)}"
