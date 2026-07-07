"""
浏览器采集器 — 从 Edge/Chrome 取回书签与历史记录

采集内容：
  - 书签分类（技术、工作、学习等兴趣方向）
  - 历史访问频率（常用网站、活跃时段）
  - 无密码、无 cookie、无个人信息
"""

import json
import logging
import os
import shutil
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alpha_id.profile_schema import AlphaIDProfile

logger = logging.getLogger(__name__)

# 常见浏览器数据目录
BROWSER_PATHS = {
    "edge": Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data" / "Default",
    "chrome": Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default",
}


def info():
    """采集器元信息 — 遵循 COLLECTOR_PROTOCOL v1.0"""
    return {
        "name": "browser",
        "display_name": "浏览器书签与历史",
        "description": "从 Edge/Chrome 本地数据中提取浏览偏好、活跃时段、兴趣领域",
        "category": "browser",
        "priority": 40,
        "requires_input": False,
    }


def detect() -> bool:
    """检测是否存在浏览器数据"""
    hits = []
    for name, profile_path in BROWSER_PATHS.items():
        if profile_path.exists():
            hits.append(name)
    return bool(hits)


def _read_bookmarks(path: Path) -> list:
    """读取浏览器书签 JSON → 返回书签列表"""
    bookmarks_file = path / "Bookmarks"
    if not bookmarks_file.exists():
        return []

    try:
        data = json.loads(bookmarks_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    results = []

    def _walk(node, folder_path=""):
        """递归遍历书签树"""
        name = node.get("name", "").strip()
        url = node.get("url", "").strip()
        if url and name:
            results.append({"name": name, "url": url, "folder": folder_path})

        children = node.get("children", [])
        for child in children:
            _walk(child, folder_path + "/" + name if name else folder_path)

    roots = data.get("roots", {})
    for root_name, root_node in roots.items():
        if isinstance(root_node, dict):
            _walk(root_node)

    return results


def _read_history(path: Path, limit: int = 1000) -> list:
    """读取浏览器历史 SQLite → 返回最近访问记录"""
    history_file = path / "History"
    if not history_file.exists():
        return []

    # 复制一份避免 SQLite 锁
    tmp = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy2(history_file, tmp)
        conn = sqlite3.connect(tmp)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()

        results = []
        for url, title, visit_time in rows:
            if not url:
                continue
            # Chrome/Edge 时间戳：1601-01-01 以来的微秒数
            try:
                dt = datetime(1601, 1, 1, tzinfo=timezone.utc) + __import__("datetime").timedelta(
                    microseconds=visit_time
                )
            except (ValueError, OverflowError):
                dt = datetime.now(timezone.utc)
            results.append(
                {
                    "url": url,
                    "title": (title or "")[:200],
                    "time": dt.isoformat(),
                }
            )
        return results
    except Exception:
        return []
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


# 技术域名 → 技术栈推断
TECH_DOMAINS = {
    "github.com": "GitHub",
    "gitlab.com": "GitLab",
    "stackoverflow.com": "Stack Overflow",
    "stackexchange.com": "Stack Exchange",
    "developer.mozilla.org": "MDN",
    "docs.python.org": "Python",
    "pypi.org": "Python",
    "npmjs.com": "Node.js",
    "crates.io": "Rust",
    "docs.rs": "Rust",
    "pkg.go.dev": "Go",
    "doc.rust-lang.org": "Rust",
    "react.dev": "React",
    "vuejs.org": "Vue",
    "angular.io": "Angular",
    "kubernetes.io": "Kubernetes",
    "docker.com": "Docker",
    "cloud.google.com": "GCP",
    "aws.amazon.com": "AWS",
    "azure.microsoft.com": "Azure",
}

# 书签分类 → 兴趣推断
INTEREST_KEYWORDS = {
    "人工智能": ["ai", "machine learning", "deep learning", "llm", "gpt", "神经网络", "人工智能"],
    "前端开发": ["react", "vue", "angular", "css", "html", "javascript", "typescript", "前端"],
    "后端开发": ["backend", "api", "微服务", "spring", "django", "flask", "fastapi"],
    "系统设计": ["architecture", "design pattern", "system design", "分布式"],
    "数据库": ["sql", "mysql", "postgresql", "mongodb", "redis", "数据库"],
    "DevOps": ["docker", "kubernetes", "ci/cd", "jenkins", "devops", "deploy"],
    "编程语言": ["python", "rust", "go", "java", "typescript", "rust"],
}


def collect() -> Optional[AlphaIDProfile]:
    """采集浏览器数据 → 生成 profile 补充"""
    # 找可用的浏览器
    browser_name = None
    browser_path = None
    for name, path in BROWSER_PATHS.items():
        if (path / "Bookmarks").exists() or (path / "History").exists():
            browser_name = name
            browser_path = path
            break

    if not browser_path:
        logger.warning("未找到浏览器数据目录")
        return None

    profile = AlphaIDProfile(
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    # 1. 书签分析
    bookmarks = _read_bookmarks(browser_path)
    tech_interests = Counter()
    all_folders = []

    for bm in bookmarks:
        url_lower = bm["url"].lower()
        name_lower = bm["name"].lower()
        folder = bm.get("folder", "")

        # 技术域名匹配
        for domain, tech in TECH_DOMAINS.items():
            if domain in url_lower:
                tech_interests[tech] += 1
                break

        # 书签分类推断
        for interest, keywords in INTEREST_KEYWORDS.items():
            for kw in keywords:
                if kw in url_lower or kw in name_lower:
                    tech_interests[interest] += 1
                    break

        if folder:
            all_folders.append(folder)

    # 2. 历史分析
    history = _read_history(browser_path, limit=500)
    tech_from_history = Counter()
    hour_counts = Counter()

    for h in history:
        url_lower = h["url"].lower()
        for domain, tech in TECH_DOMAINS.items():
            if domain in url_lower:
                tech_from_history[tech] += 1
                break
        try:
            dt = datetime.fromisoformat(h["time"])
            hour_counts[dt.hour] += 1
        except Exception:
            pass

    # 3. 合并到画像
    # 技术兴趣
    all_techs = tech_interests + tech_from_history
    top_techs = [tech for tech, _ in all_techs.most_common(10)]

    # 推断编程语言（书签 + 历史）
    lang_keywords = {
        "Python": ["python", "pypi", "docs.python"],
        "TypeScript": ["typescript", "ts"],
        "JavaScript": ["javascript", "js", "npm"],
        "Rust": ["rust", "crates.io", "docs.rs"],
        "Java": ["java", "spring", "maven"],
        "Go": ["go", "golang"],
        "Kubernetes": ["kubernetes", "k8s"],
        "Docker": ["docker"],
    }
    detected_langs = []
    for lang, keywords in lang_keywords.items():
        for kw in keywords:
            if any(kw in bm["url"].lower() for bm in bookmarks) or any(kw in h["url"].lower() for h in history):
                detected_langs.append(lang)
                break

    if detected_langs:
        profile.persona.technical.primary_languages = list(dict.fromkeys(detected_langs))[:8]

    # 框架偏好（书签 + 历史）
    frameworks = []
    for bm in bookmarks:
        url = bm["url"].lower()
        if "react" in url:
            frameworks.append("React")
        elif "vue" in url:
            frameworks.append("Vue")
        elif "spring" in url:
            frameworks.append("Spring")
        elif "django" in url:
            frameworks.append("Django")
    for h in history:
        url = h["url"].lower()
        if "react" in url:
            frameworks.append("React")
        elif "vue" in url:
            frameworks.append("Vue")
        elif "spring" in url:
            frameworks.append("Spring")
        elif "django" in url:
            frameworks.append("Django")
    if frameworks:
        profile.persona.technical.framework_preferences = list(dict.fromkeys(frameworks))[:5]

    # 沟通风格（浏览行为推断）
    if len(history) > 50:
        profile.persona.communication.sentence_length = "medium"
    else:
        profile.persona.communication.sentence_length = "short"

    if hour_counts:
        peak = max(hour_counts.values())
        if peak > 10:
            profile.persona.communication.tone = "focused"

    # 活跃时段
    if hour_counts:
        profile.persona.communication.active_hours = sorted(h for h, _ in hour_counts.most_common(8))

    # 工作节奏
    if hour_counts:
        night = sum(c for h, c in hour_counts.items() if h >= 22 or h <= 5)
        day = sum(c for h, c in hour_counts.items() if 6 <= h <= 18)
        total = night + day
        if total > 0:
            profile.persona.temporal.work_rhythm = "night_owl" if night / total > 0.35 else "daytime"

    # 元信息
    profile.extra["source"] = "browser"
    profile.extra["browser"] = browser_name
    profile.extra["bookmark_count"] = len(bookmarks)
    profile.extra["history_count"] = len(history)
    profile.extra["tech_interests"] = top_techs[:5]

    return profile


def summary(profile: AlphaIDProfile) -> str:
    """采集摘要"""
    browser = profile.extra.get("browser", "?")
    bm = profile.extra.get("bookmark_count", 0)
    hist = profile.extra.get("history_count", 0)
    interests = profile.extra.get("tech_interests", [])
    lines = [
        f"[浏览器] {browser} 浏览记录采集",
        f"   书签: {bm} 个",
        f"   历史: {hist} 条",
    ]
    if interests:
        lines.append(f"   技术兴趣: {', '.join(interests)}")
    return "\n".join(lines)
