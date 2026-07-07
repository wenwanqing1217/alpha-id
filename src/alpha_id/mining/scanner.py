"""Mining scanner — 扫描目标路径，找出可提取画像的数字痕迹。"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SourceHint:
    """单个可采集源的线索"""

    kind: str
    path: str
    label: str
    confidence: int = 50
    meta: Dict[str, object] = field(default_factory=dict)


@dataclass
class ScanReport:
    """一次 scan_path 的结果"""

    root: str
    sources: List[SourceHint] = field(default_factory=list)

    def top_sources(self, max_count: int = 20) -> List[SourceHint]:
        return sorted(self.sources, key=lambda item: item.confidence, reverse=True)[:max_count]


def scan_path(root: Optional[str] = None) -> ScanReport:
    """扫描指定目录，返回画像线索。"""

    scan_root = Path(root) if root else Path.cwd()
    report = ScanReport(root=str(scan_root))

    _scan_git_roots(scan_root, report)
    _scan_chat_exports(scan_root, report)
    _scan_code_signals(scan_root, report)
    _scan_browser_bookmark_signals(scan_root, report)

    logger.info("scan_path complete: %s sources from %s", len(report.sources), scan_root)
    return report


def _scan_git_roots(scan_root: Path, report: ScanReport) -> None:
    for git_dir in scan_root.rglob(".git"):
        if git_dir.is_dir():
            repo = git_dir.parent
            report.sources.append(
                SourceHint(
                    kind="git_repo",
                    path=str(repo),
                    label=str(repo),
                    confidence=85,
                    meta={"hint": "git history + code structure"},
                )
            )


def _scan_chat_exports(scan_root: Path, report: ScanReport) -> None:
    for match in scan_root.rglob("*"):
        if match.is_file() and match.suffix.lower() in {".zip", ".json"}:
            name = match.name.lower()
            if "chatgpt" in name or "claude" in name:
                kind = "chatgpt_export" if "chatgpt" in name else "claude_export"
                report.sources.append(
                    SourceHint(
                        kind=kind,
                        path=str(match),
                        label=str(match),
                        confidence=95,
                        meta={"suffix": match.suffix.lower()},
                    )
                )


def _scan_code_signals(scan_root: Path, report: ScanReport) -> None:
    exts = {".py", ".js", ".ts", ".rs", ".go", ".java", ".rb", ".php", ".c", ".cpp", ".h"}
    found: Dict[str, int] = {}
    for match in scan_root.rglob("*"):
        if match.is_file() and match.suffix.lower() in exts:
            found[match.suffix.lower()] = found.get(match.suffix.lower(), 0) + 1
    for ext, count in sorted(found.items(), key=lambda item: item[1], reverse=True)[:8]:
        report.sources.append(
            SourceHint(
                kind="code_extension",
                path=str(scan_root),
                label=f"{ext} files ({count})",
                confidence=45,
                meta={"extension": ext, "count": count},
            )
        )


def _scan_browser_bookmark_signals(scan_root: Path, report: ScanReport) -> None:
    for match in scan_root.rglob("*"):
        if match.is_file() and match.suffix.lower() in {".html", ".json", ".csv"}:
            name = match.name.lower()
            if "bookmark" in name or "history" in name:
                report.sources.append(
                    SourceHint(
                        kind="browser_artifact",
                        path=str(match),
                        label=str(match),
                        confidence=60,
                        meta={"suffix": match.suffix.lower()},
                    )
                )
