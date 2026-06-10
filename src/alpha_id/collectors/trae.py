"""
Trae CN 采集器 — 从字节跳动 AI IDE 中取回你的代码痕迹

采集内容：
  - 工作区项目（名称、路径、语言）
  - 编辑历史（活跃时段、文件类型）
  - 无代码内容，只取元数据
"""
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alpha_id.profile_schema import AlphaIDProfile

logger = logging.getLogger(__name__)

TRAE_USER_DIR = Path.home() / "AppData" / "Roaming" / "Trae CN" / "User"


def info():
    """采集器元信息 — 遵循 COLLECTOR_PROTOCOL v1.0"""
    return {
        "name": "trae",
        "display_name": "Trae CN IDE",
        "description": "从 Trae CN 本地工作空间和编辑记录中提取编码习惯和项目偏好",
        "category": "ide",
        "priority": 35,
        "requires_input": False,
    }


def detect() -> bool:
    """检测是否存在 Trae CN 数据"""
    return TRAE_USER_DIR.exists()


def _find_workspaces():
    """扫描 Trae 的所有工作区"""
    ws_dir = TRAE_USER_DIR / "workspaceStorage"
    if not ws_dir.exists():
        return []
    workspaces = []
    for entry in sorted(ws_dir.iterdir()):
        if entry.is_dir():
            ws_file = entry / "workspace.json"
            if ws_file.exists():
                try:
                    data = json.loads(ws_file.read_text(encoding="utf-8"))
                    folder = data.get("folder", "")
                    name = Path(folder).name if folder else entry.name[:8]
                    workspaces.append({"name": name, "folder": folder, "id": entry.name})
                except Exception:
                    pass
    return workspaces


def _scan_history_extensions():
    """扫描编辑历史中的文件类型→推断编程语言"""
    hist_dir = TRAE_USER_DIR / "History"
    if not hist_dir.exists():
        return [], []

    exts = Counter()
    active_dates = set()

    for session_dir in hist_dir.iterdir():
        if not session_dir.is_dir():
            continue
        for f in session_dir.iterdir():
            if f.is_file() and "." in f.name:
                # 文件名是随机字符如 "2NNG.wxss"，取扩展名
                ext = f.suffix.lower()
                if ext and len(ext) <= 10 and ext[1:].isalnum():
                    exts[ext] += 1
            # 记录活跃时间
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            active_dates.add(mtime.strftime("%Y-%m-%d %H:00"))

    return exts, active_dates


# 扩展名 → 编程语言映射
EXT_TO_LANG = {
    ".py": "Python", ".pyw": "Python", ".ipynb": "Python",
    ".js": "JavaScript", ".jsx": "React", ".ts": "TypeScript", ".tsx": "React",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java", ".kt": "Kotlin",
    ".cpp": "C++", ".c": "C", ".h": "C/C++", ".hpp": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".rb": "Ruby",
    ".php": "PHP",
    ".vue": "Vue",
    ".css": "CSS", ".scss": "SCSS", ".less": "Less",
    ".html": "HTML", ".htm": "HTML",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
    ".md": "Markdown", ".rst": "reStructuredText",
    ".sql": "SQL",
    ".sh": "Shell", ".bat": "Batch", ".ps1": "PowerShell",
    ".toml": "TOML",
    ".xml": "XML",
    ".wxss": "WeChat StyleSheet", ".wxml": "WeChat Template",
}


def collect() -> Optional[AlphaIDProfile]:
    """采集 Trae 数据 → 生成 profile 补充"""
    if not TRAE_USER_DIR.exists():
        logger.warning("未找到 Trae 数据目录")
        return None

    profile = AlphaIDProfile(
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    # 1. 工作区信息
    workspaces = _find_workspaces()
    languages_used = set()

    for ws in workspaces:
        folder = ws.get("folder", "")
        if folder:
            # 从文件夹路径推断语言
            for ext, lang in EXT_TO_LANG.items():
                if any(f.endswith(ext) for f in Path(folder).rglob("*") if f.is_file()):
                    languages_used.add(lang)

    # 2. 编辑历史
    exts, active_dates = _scan_history_extensions()

    # 3. 合并画像
    # 主要语言
    all_langs = list(languages_used)
    for ext, count in exts.most_common(20):
        lang = EXT_TO_LANG.get(ext)
        if lang and lang not in all_langs:
            all_langs.append(lang)
    profile.persona.technical.primary_languages = all_langs[:8]

    # 编码风格
    has_ts = any("TypeScript" in lang for lang in all_langs)
    has_fp_langs = any(lang in all_langs for lang in ["Rust", "Haskell", "Scala"])
    if has_fp_langs:
        profile.persona.technical.coding_style = "functional"
    elif has_ts:
        profile.persona.technical.coding_style = "typed"
    else:
        profile.persona.technical.coding_style = "mixed"

    # 框架偏好
    frameworks = []
    for ext in exts:
        if ext == ".vue":
            frameworks.append("Vue")
        elif ext in (".jsx", ".tsx"):
            frameworks.append("React")
        elif ext == ".py":
            frameworks.append("Python")
    if frameworks:
        profile.persona.technical.framework_preferences = list(set(frameworks))[:5]

    # 活跃时段
    if active_dates:
        hours = Counter()
        for d in active_dates:
            try:
                h = int(d.split()[1].split(":")[0])
                hours[h] += 1
            except (ValueError, IndexError):
                pass
        if hours:
            profile.persona.communication.active_hours = sorted(h for h, _ in hours.most_common(8))

    # 工作节奏
    if hours:
        night = sum(c for h, c in hours.items() if h >= 22 or h <= 5)
        day = sum(c for h, c in hours.items() if 6 <= h <= 18)
        total = night + day
        if total > 0:
            profile.persona.temporal.work_rhythm = (
                "night_owl" if night / total > 0.35 else "daytime"
            )

    # 元信息
    profile.extra["source"] = "trae"
    profile.extra["workspace_count"] = len(workspaces)
    profile.extra["history_entries"] = sum(1 for _ in exts.elements())

    return profile


def summary(profile: AlphaIDProfile) -> str:
    """采集摘要"""
    ws = profile.extra.get("workspace_count", 0)
    he = profile.extra.get("history_entries", 0)
    lines = [
        "[Trae] 代码痕迹采集",
        f"   工作区: {ws} 个",
        f"   编辑记录: {he} 条",
        f"   主要语言: {', '.join(profile.persona.technical.primary_languages[:5]) if profile.persona.technical.primary_languages else '未知'}",
    ]
    if profile.persona.technical.coding_style:
        lines.append(f"   编码风格: {profile.persona.technical.coding_style}")
    return "\n".join(lines)
