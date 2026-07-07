"""
aid detect — 扫描本机 AI 工具与数据源

不是让工具认识你，是把你散在各处的数字痕迹找回来。
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

DataSource = Dict[str, object]


def _check_trae() -> Optional[DataSource]:
    """Trae CN - 字节跳动 AI IDE"""
    data_dir = Path(os.environ.get("APPDATA", "")) / "Trae CN"
    user_dir = data_dir / "User"
    if user_dir.exists():
        # 可能的数据源
        sources = []
        history = user_dir / "History"
        if history.exists():
            sources.append({"type": "history", "path": str(history), "collect_cmd": "aid collect trae"})
        workspace = user_dir / "workspaceStorage"
        if workspace.exists():
            sources.append({"type": "workspaces", "path": str(workspace), "collect_cmd": "aid collect trae"})
        return {
            "name": "Trae CN",
            "data_dir": str(user_dir),
            "sources": sources,
        }
    return None


def _check_codex() -> Optional[DataSource]:
    """OpenAI Codex - 微软商店版"""
    try:
        r = subprocess.run(
            [
                "powershell",
                "-Command",
                "Get-AppxPackage -Name 'OpenAI.Codex' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty PackageFullName",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.stdout.strip():
            # Codex 数据在 LocalCache 里，但 LevelDB 格式目前不可读
            return {
                "name": "Codex (OpenAI)",
                "data_dir": str(Path(os.environ.get("LOCALAPPDATA", "")) / "Packages" / "OpenAI.Codex_2p2nqsd0c76g0"),
                "sources": [],
                "note": "数据存于 LevelDB（二进制），暂不支持自动采集",
            }
    except Exception:
        pass
    return None


def _check_codexplusplus() -> Optional[DataSource]:
    """Codex++ - 脚本管理器"""
    scripts_file = Path(os.environ.get("APPDATA", "")) / "Codex++" / "user_scripts.json"
    if scripts_file.exists():
        return {
            "name": "Codex++",
            "data_dir": str(scripts_file.parent),
            "sources": [{"type": "user_scripts", "path": str(scripts_file), "collect_cmd": None}],
            "note": "用户脚本元数据，非个人数据痕迹",
        }
    return None


def _check_chatgpt() -> Optional[DataSource]:
    """ChatGPT（本机导出目录检查）"""
    # 常见 ChatGPT 导出位置
    for p in [
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path.home() / ".alpha-id",
    ]:
        for f in p.glob("*chatgpt*"):
            if f.suffix in (".zip", ".json"):
                return {
                    "name": "ChatGPT",
                    "data_dir": str(f.parent),
                    "sources": [{"type": "export", "path": str(f), "collect_cmd": f"aid collect chatgpt {f}"}],
                }
    return None


def _check_browser() -> Optional[DataSource]:
    """浏览器 - 书签/历史"""
    browsers = []
    # Edge
    edge_data = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data"
    if edge_data.exists():
        browsers.append("Edge")
    # Chrome
    chrome_data = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    if chrome_data.exists():
        browsers.append("Chrome")
    # 国产浏览器...
    if browsers:
        return {
            "name": "浏览器",
            "data_dir": None,
            "sources": [{"type": "bookmarks", "collect_cmd": "aid collect browser"}],
            "note": f"发现 {', '.join(browsers)}，可采集书签/历史",
        }
    return None


def _check_git() -> Optional[DataSource]:
    """本地 Git 仓库"""
    try:
        from alpha_id.collectors.git import GitCollector

        if GitCollector().detect():
            return {
                "name": "Git",
                "data_dir": None,
                "sources": [{"type": "repositories", "collect_cmd": "aid collect git"}],
            }
    except Exception:
        pass
    return None


DETECTORS = [
    ("AI 编程工具", [_check_trae, _check_codex, _check_codexplusplus]),
    ("聊天数据", [_check_chatgpt]),
    ("浏览器数据", [_check_browser]),
    ("版本控制", [_check_git]),
]


def _get_collected_sources() -> set:
    """读取 profile 中已采集的源名称集合"""
    try:
        from alpha_id.profile_schema import load_profile

        profile = load_profile()
        if profile and hasattr(profile, "extra") and isinstance(profile.extra, dict):
            sources = profile.extra.get("x_collected_sources", [])
            if isinstance(sources, list):
                return {str(s).lower() for s in sources}
    except Exception:
        pass
    return set()


def scan() -> List[dict]:
    """扫描所有数据源，按类别分组"""
    results = []
    for category, detectors in DETECTORS:
        items = []
        for detect in detectors:
            try:
                info = detect()
                if info:
                    items.append(info)
            except Exception:
                pass
        if items:
            results.append({"category": category, "items": items})
    return results


def format_report(groups: List[dict]) -> str:
    """生成可读报告"""
    if not groups:
        return "未检测到可采集的数据源"

    # 读取已采集列表
    collected = _get_collected_sources()

    lines = []
    lines.append("=" * 45)
    lines.append("  数据源扫描报告")
    lines.append("  找到你在各工具中的数字痕迹")
    lines.append("=" * 45)
    lines.append("")

    for group in groups:
        lines.append(f"【{group['category']}】")
        for item in group["items"]:
            name = item["name"]
            # 去重标记：已采集的源加 [已采集 ✓]
            name_lower = name.lower()
            is_collected = any(c in name_lower or name_lower in c for c in collected)
            label = f"{name}  [已采集 ✓]" if is_collected else name
            lines.append(f"  {label}")
            if item.get("note"):
                lines.append(f"    └ {item['note']}")
            if item.get("sources"):
                for src in item["sources"]:
                    if src.get("collect_cmd"):
                        lines.append(f"    └ 采集: {src['collect_cmd']}")
        lines.append("")

    if not collected:
        lines.append("提示: 选择上面列出的采集命令来取回你的数据")
    else:
        lines.append("提示: [已采集] 标记的数据源可再次运行采集命令更新画像")
    return "\n".join(lines)
