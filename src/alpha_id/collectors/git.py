"""Git 仓库采集器"""

import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alpha_id.collectors.base import BaseCollector, CollectorInfo
from alpha_id.profile_schema import AlphaIDProfile

logger = logging.getLogger(__name__)


def _common_roots():
    return [
        Path.home() / "projects",
        Path.home() / "code",
        Path.home() / "repos",
        Path.cwd(),
    ]


def _find_repo():
    for root in _common_roots():
        if not root.exists():
            continue
        for git_dir in root.rglob(".git"):
            if git_dir.is_dir():
                return git_dir.parent
    return None


class GitCollector(BaseCollector):
    info = CollectorInfo(
        name="git",
        display_name="Git 仓库",
        description="从本地 Git 仓库提取提交历史、语言偏好和协作模式",
        category="version_control",
        priority=25,
        requires_input=False,
    )

    def detect(self) -> bool:
        return _find_repo() is not None

    def detect_for_path(self, repo_path: Path) -> bool:
        try:
            return (Path(repo_path) / ".git").exists()
        except Exception:
            return False

    def collect_for_path(self, repo_path: Path) -> Optional[AlphaIDProfile]:
        repo = Path(repo_path)
        if repo is None:
            return None

        profile = AlphaIDProfile(
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        exts = Counter()
        languages = Counter()
        try:
            for f in repo.rglob("*"):
                if f.is_file() and f.suffix:
                    ext = f.suffix.lower()
                    exts[ext] += 1
        except Exception:
            pass

        ext_to_lang = {
            ".py": "Python",
            ".pyw": "Python",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".rs": "Rust",
            ".go": "Go",
            ".java": "Java",
            ".rb": "Ruby",
            ".php": "PHP",
        }
        for ext, count in exts.most_common(20):
            lang = ext_to_lang.get(ext)
            if lang:
                languages[lang] += count

        if languages:
            profile.persona.technical.primary_languages = [lang for lang, _ in languages.most_common(8)]

        frameworks = []
        if any(ext == ".vue" for ext in exts):
            frameworks.append("Vue")
        if any(ext in (".jsx", ".tsx") for ext in exts):
            frameworks.append("React")
        if ".py" in exts:
            frameworks.append("Python")
        if frameworks:
            profile.persona.technical.framework_preferences = list(dict.fromkeys(frameworks))[:5]

        profile.extra["source"] = "git"
        profile.extra["repo"] = str(repo)
        profile.extra["file_count"] = sum(1 for _ in repo.rglob("*") if _.is_file())
        return profile

    def summary(self, profile: AlphaIDProfile) -> str:
        repo = profile.extra.get("repo", "?")
        langs = profile.persona.technical.primary_languages or []
        lines = [
            "[Git] 仓库痕迹采集",
            f"   仓库: {repo}",
            f"   主要语言: {', '.join(langs[:5]) if langs else '未知'}",
        ]
        if profile.persona.technical.framework_preferences:
            lines.append(f"   框架: {', '.join(profile.persona.technical.framework_preferences)}")
        return "\n".join(lines)
