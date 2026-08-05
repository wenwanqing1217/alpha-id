"""
NURO 主动观察 — 主动感知用户行为（无需唤醒词）

循环检测：
- 当前窗口标题（知道用户在做什么）
- 屏幕截图（可选，眼瞎模式下禁用）
- 时间上下文（工作时间/休息时间）

输出：场景类型 + 观察摘要 → 触发相应的 NURO 行为
"""

import logging
import os
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

OBSERVE_INTERVAL = 30  # 秒（可通过 settings 扩展）


class SceneType(Enum):
    """场景类型"""
    WORKING = "working"       # 工作（IDE、文档）
    BROWSING = "browsing"     # 浏览网页
    CHATTING = "chatting"     # 聊天/社交
    GAMING = "gaming"         # 游戏
    IDLE = "idle"             # 空闲
    UNKNOWN = "unknown"       # 未知


class FairyObserver:
    """
    主动观察循环

    通过检测当前活动窗口来判断用户场景，
    不依赖唤醒词，无需始终监听麦克风。
    """

    # 窗口标题关键词 → 场景映射
    SCENE_KEYWORDS: Dict[SceneType, list] = {
        SceneType.WORKING: ["vscode", "pycharm", "idea", "visual studio", "excel", "word",
                           "powerpoint", "terminal", "cmd", "powershell"],
        SceneType.BROWSING: ["chrome", "firefox", "edge", "safari", "browser"],
        SceneType.CHATTING: ["wechat", "qq", "telegram", "discord", "slack", "teams",
                            "whatsapp", "微信", "钉钉"],
        SceneType.GAMING: ["steam", "game", "epic", "origin", "battle.net"],
    }

    def __init__(self, callback: Optional[Callable[[SceneType, Dict[str, Any]], None]] = None,
                 interval: int = OBSERVE_INTERVAL, blind: bool = False,
                 brain=None, memory=None):
        """
        Args:
            callback: 观察回调 (scene_type, info_dict) -> None
            interval: 观察间隔（秒）
            blind: 眼瞎模式（不截图，仅窗口标题）
            brain: FairyBrain 实例（用于场景分析）
            memory: FairyMemory 实例（用于记录活动）
        """
        self.callback = callback
        self.blind = blind
        self.brain = brain
        self.memory = memory
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_scene = SceneType.UNKNOWN

        # 回调别名（兼容 daemon 调用）
        self.on_scene_change = None      # Callable[[SceneType, Dict], None]
        self.on_notification = None      # Callable[[str], None]
        self.on_sensitive_detected = None  # Callable[[str], None]

        # 配置对象（兼容 daemon .config.interval 访问）
        self.config = type('Config', (), {'interval': interval})()
        self.interval = interval

    def start(self):
        """启动观察循环"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._observe_loop, daemon=True)
        self._thread.start()
        logger.info(f"主动观察启动: interval={self.interval}s, blind={self.blind}")

    def stop(self):
        """停止观察"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def _observe_loop(self):
        """主观察循环"""
        while self._running:
            try:
                scene, info = self._detect_scene()
                if scene != self._last_scene:
                    self._last_scene = scene
                    if self.callback:
                        self.callback(scene, info)
                    logger.info(f"场景变化: {scene.value} → {info.get('title', '')}")
            except Exception as e:
                logger.error(f"观察异常: {e}")
            time.sleep(self.interval)

    def _detect_scene(self) -> tuple:
        """
        检测当前场景

        Returns:
            (SceneType, info_dict)
        """
        title = self._get_active_window_title()
        title_lower = title.lower()

        # 关键词匹配
        for scene, keywords in self.SCENE_KEYWORDS.items():
            for kw in keywords:
                if kw in title_lower:
                    return scene, {"title": title, "matched_keyword": kw}

        return SceneType.IDLE if not title else SceneType.UNKNOWN, {"title": title}

    def _get_active_window_title(self) -> str:
        """获取当前活动窗口标题"""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""

    def get_screenshot(self, path: Optional[str] = None) -> str:
        """
        屏幕截图（Computer Use 视觉输入）

        Args:
            path: 保存路径，默认临时文件

        Returns:
            截图文件路径
        """
        if self.blind:
            logger.debug("眼瞎模式：跳过截图")
            return ""

        if not path:
            path = os.path.join(os.getenv("TEMP", "/tmp"), "fairy_screenshot.png")

        try:
            import pyautogui
            img = pyautogui.screenshot()
            img.save(path)
            return path
        except ImportError:
            logger.warning("pyautogui 未安装，截图不可用")
            return ""
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return ""
