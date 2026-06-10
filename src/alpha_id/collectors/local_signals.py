"""
本机信号采集器 — 零数据冷启动

无导出数据时，扫描本机数字痕迹（shell 历史/git 提交/文件后缀/书签）
30 秒内生成初始画像。对应 55.md L1/L2 分层扫描策略。
"""

import logging
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alpha_id.collectors.base import BaseCollector, CollectorInfo
from alpha_id.profile_schema import AlphaIDProfile

logger = logging.getLogger(__name__)


class LocalSignalsCollector(BaseCollector):
    """扫描本机文件系统信号，生成初始画像。L1 (0-30s) 实现。"""

    info = CollectorInfo(
        name="local_signals",
        display_name="本机信号扫描",
        description="无导出数据时的零数据冷启动：扫描 shell 历史/git 提交/文件后缀/书签",
        category="local",
        priority=100,
        requires_input=False,
    )

    def detect(self) -> bool:
        """总能检测到（任何操作系统都有基本可扫描内容）"""
        return True

    def collect(self, input_path: Optional[Path] = None) -> Optional[AlphaIDProfile]:
        profile = AlphaIDProfile(created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

        # L1: shell 历史 → 活跃时段 + 技术语言
        shell_words = self._scan_shell_history()
        if shell_words:
            self._infer_languages(profile, shell_words)

        # L2: git 提交 → 活跃时段
        commit_hours = self._scan_git_commits()
        all_hours = commit_hours[:]

        # L2: 文件后缀 → 技术栈
        file_patterns = self._scan_file_extensions()
        if file_patterns:
            self._infer_languages(profile, list(file_patterns.keys()))

        # 活跃时段：优先从 git 推断，没有就从时间推断
        if all_hours:
            profile.persona.communication.active_hours = sorted(all_hours[:5])

        # 无数据 → 返回空 profile（调用方应处理）
        if not profile.persona.technical.primary_languages and not all_hours:
            return profile

        # 基本推测
        if not profile.persona.communication.tone:
            profile.persona.communication.tone = "direct"
        if not profile.persona.communication.sentence_length:
            profile.persona.communication.sentence_length = "medium"

        # 工作节奏
        if all_hours:
            night = sum(1 for h in all_hours if h >= 22 or h <= 5)
            day = sum(1 for h in all_hours if 6 <= h <= 18)
            if night + day > 0:
                profile.persona.temporal.work_rhythm = "night_owl" if night / (night + day) > 0.4 else "daytime"

        return profile

    def summary(self, profile: AlphaIDProfile) -> str:
        lines = ["[本机信号] 零数据冷启动扫描"]
        if profile.persona.technical.primary_languages:
            lines.append(f"   检测到语言: {', '.join(profile.persona.technical.primary_languages)}")
        if profile.persona.communication.active_hours:
            lines.append(f"   推测活跃时段: {', '.join(f'{h:02d}:00' for h in profile.persona.communication.active_hours[:5])}")
        if profile.persona.temporal.work_rhythm:
            lines.append(f"   推测工作节奏: {profile.persona.temporal.work_rhythm}")
        return "\n".join(lines)

    def _scan_shell_history(self) -> list[str]:
        """L1: 扫描 shell 历史（bash/zsh/PowerShell）"""
        words = []
        for hist_path in [
            Path.home() / ".bash_history",
            Path.home() / ".zsh_history",
            Path.home() / ".python_history",
            Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt",
        ]:
            try:
                if hist_path.exists():
                    with open(hist_path, errors="ignore") as f:
                        for line in list(f)[-500:]:
                            words.extend(line.strip().split()[:5])
                if len(words) > 500:
                    break
            except Exception:
                pass
        return words[-2000:]

    def _scan_git_commits(self) -> list[int]:
        """L2: 扫描 git 提交时间 → 活跃时段"""
        hours = []
        for git_dir in [Path.home() / "projects", Path.home() / "dev", Path.home() / "code"]:
            if not git_dir.exists():
                continue
            for git_repo in git_dir.glob("*/.git"):
                log_path = git_repo.parent / ".git" / "logs" / "HEAD"
                try:
                    if log_path.exists():
                        with open(log_path, errors="ignore") as f:
                            for line in list(f)[-200:]:
                                # git log format: <old> <new> <name> <email> <timestamp> <tz> ...
                                parts = line.split()
                                if len(parts) >= 5:
                                    ts = int(parts[-2])
                                    hours.append(datetime.fromtimestamp(ts).hour)
                    if len(hours) > 100:
                        break
                except Exception:
                    pass
        return sorted(hours)

    def _scan_file_extensions(self) -> Counter:
        """L2: 扫描常用目录的文件扩展名 → 技术栈"""
        extensions = Counter()
        for scan_dir in [Path.home() / "projects", Path.home() / "dev", Path.home() / "code"]:
            if not scan_dir.exists():
                continue
            try:
                for f in list(scan_dir.rglob("*"))[:2000]:
                    if f.is_file() and not any(p in str(f) for p in (".git", "node_modules", "__pycache__", ".venv")):
                        ext = f.suffix.lower()
                        if ext in _EXT_TO_LANG:
                            extensions[_EXT_TO_LANG[ext]] += 1
            except PermissionError:
                pass
        return extensions

    def _infer_languages(self, profile: AlphaIDProfile, words: list[str]):
        """从单词列表推断编程语言"""
        detected = set()
        text = " ".join(words).lower()
        for lang, pattern in _LANG_PATTERNS.items():
            if re.search(pattern, text):
                detected.add(lang)
        # 排序：已检测 + 新检测
        existing = set(profile.persona.technical.primary_languages or [])
        profile.persona.technical.primary_languages = list(dict.fromkeys(list(existing) + list(detected)))[:5]


_EXT_TO_LANG = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".vue": "TypeScript",
    ".svelte": "JavaScript",
}

_LANG_PATTERNS = {
    "Python": r"\b(python|pip|pytest|django|flask|fastapi)\b",
    "TypeScript": r"\b(npm|typescript|tsc|next\.js|react)\b",
    "JavaScript": r"\b(node|npm|javascript|js)\b",
    "Rust": r"\b(cargo|rustc|rust)\b",
    "Go": r"\b(go mod|go build|golang)\b",
    "Java": r"\b(maven|gradle|java)\b",
}


_instance = LocalSignalsCollector()
info, detect, collect, summary = _instance.create_module_functions()
