"""
场景识别 — Phase 1 任务 #6

硬编码规则：窗口标题/文件后缀/当前时间 → 判断场景。
供 daemon 做 Profile 注入用（Phase 2）。
"""

import os
from datetime import datetime
from enum import Enum
from typing import Optional


class Scene(Enum):
    CODING = "coding"
    EMAIL = "email"
    CHAT = "chat"
    BROWSING = "browsing"
    WRITING = "writing"
    TERMINAL = "terminal"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        labels = {
            Scene.CODING: "写代码",
            Scene.EMAIL: "写邮件",
            Scene.CHAT: "聊天",
            Scene.BROWSING: "浏览网页",
            Scene.WRITING: "写作",
            Scene.TERMINAL: "命令行",
            Scene.UNKNOWN: "未知",
        }
        return labels.get(self, "未知")

    @property
    def inject_profile(self) -> str:
        """建议注入的画像类型"""
        inject_map = {
            Scene.CODING: "technical",
            Scene.EMAIL: "communication",
            Scene.CHAT: "communication",
            Scene.BROWSING: "mixed",
            Scene.WRITING: "communication",
            Scene.TERMINAL: "technical",
            Scene.UNKNOWN: "mixed",
        }
        return inject_map.get(self, "mixed")


def detect_scene(window_title: Optional[str] = None, file_path: Optional[str] = None) -> tuple[Scene, dict]:
    """检测当前场景

    Args:
        window_title: 活跃窗口标题（daemon 获取）
        file_path: 当前打开的文件路径

    Returns:
        (Scene, 额外信息)
    """
    title = (window_title or "").lower()
    fp = (file_path or "").lower()
    info = {}

    # 1. 窗口标题检测
    ide_keywords = ["visual studio code", "pycharm", "intellij", "vim", "neovim",
                    "cursor", "trae", "zed", "sublime", "atom", "d:"]
    email_keywords = ["outlook", "gmail", "mail", "thunderbird", "邮件"]
    chat_keywords = ["slack", "discord", "wechat", "微信", "telegram", "signal",
                     "chatgpt", "claude", "deepseek", "copilot"]
    terminal_keywords = ["terminal", "powershell", "cmd", "bash", "zsh", "wsl",
                         "命令提示符"]

    for kw in ide_keywords:
        if kw in title:
            info["window"] = kw
            return Scene.CODING, info
    for kw in email_keywords:
        if kw in title:
            info["window"] = kw
            return Scene.EMAIL, info
    for kw in chat_keywords:
        if kw in title:
            info["window"] = kw
            return Scene.CHAT, info
    for kw in terminal_keywords:
        if kw in title:
            info["window"] = kw
            return Scene.TERMINAL, info

    # 2. 文件后缀检测
    code_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".java",
                       ".c", ".cpp", ".h", ".vue", ".svelte", ".rb", ".php", ".swift"}
    doc_extensions = {".md", ".txt", ".rst", ".doc", ".docx", ".pdf", ".tex", ".org"}
    email_extensions = {".eml", ".msg"}

    if fp:
        ext = os.path.splitext(fp)[1]
        if ext in code_extensions:
            info["extension"] = ext
            return Scene.CODING, info
        if ext in doc_extensions:
            info["extension"] = ext
            return Scene.WRITING, info
        if ext in email_extensions:
            info["extension"] = ext
            return Scene.EMAIL, info

    # 3. 时间检测
    hour = datetime.now().hour
    if 2 <= hour <= 5:
        info["time"] = f"{hour:02d}:00"
        return Scene.CODING, info  # 凌晨大概率在写代码

    return Scene.UNKNOWN, info


def format_scene_report(scene: Scene, info: dict) -> str:
    """生成人类可读场景报告"""
    lines = [f"当前场景: {scene.label}"]
    for k, v in info.items():
        lines.append(f"  检测依据: {k}={v}")
    lines.append(f"  建议注入画像: {scene.inject_profile}")
    return "\\n".join(lines)
