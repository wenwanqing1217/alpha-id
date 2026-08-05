"""
Alpha-ID Agent Feed — 资讯采集模块
====================================

为 Agent 提供"养料"：
  - AI 行业动态
  - GitHub 趋势
  - 技术论文/博客
  - 用户关注项目的更新

设计原则：
  - 不是给人看的资讯，是给 Agent 学习的资讯
  - Agent 判断相关性，自动学习或丢弃
  - 所有资讯经过 LLM 提炼，只保留对 Agent 有用的

数据来源：
  - GitHub Trending / API
  - Hacker News
  - ArXiv AI 论文
  - 用户 Star 的项目
  - RSS 技术博客
"""

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FeedItem:
    """单条资讯"""
    id: str = ""
    title: str = ""
    summary: str = ""
    source: str = ""           # github / hackernews / arxiv / rss
    url: str = ""
    published_at: str = ""
    tags: List[str] = field(default_factory=list)
    relevance_score: float = 0.0  # 0-1，Agent 评估的相关性
    learned: bool = False         # Agent 是否已学习
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FeedConfig:
    """Feed 配置"""
    github_token: str = ""
    hackernews_enabled: bool = True
    arxiv_enabled: bool = True
    rss_feeds: List[str] = field(default_factory=list)
    star_watch_enabled: bool = True
    fetch_interval_minutes: int = 60
    max_items_per_fetch: int = 20
    relevance_threshold: float = 0.6  # 低于此分数丢弃


class AgentFeed:
    """
    Agent 资讯采集器

    用法：
        feed = AgentFeed(config)
        items = feed.fetch_latest()
        for item in items:
            agent.learn(item)
    """

    def __init__(self, config: Optional[FeedConfig] = None):
        self.config = config or FeedConfig()
        self._items: List[FeedItem] = []
        self._callbacks: List[Callable] = []
        self._last_fetch: float = 0
        self._stats = {"fetched": 0, "learned": 0, "discarded": 0}

    def on_new_item(self, callback: Callable[[FeedItem], None]):
        """注册新资讯回调"""
        self._callbacks.append(callback)

    def fetch_latest(self) -> List[FeedItem]:
        """获取最新资讯（所有来源）"""
        items: List[FeedItem] = []

        # GitHub Trending
        try:
            items.extend(self._fetch_github_trending())
        except Exception as e:
            logger.warning("GitHub fetch failed: %s", e)

        # Hacker News
        if self.config.hackernews_enabled:
            try:
                items.extend(self._fetch_hackernews())
            except Exception as e:
                logger.warning("HN fetch failed: %s", e)

        # ArXiv AI
        if self.config.arxiv_enabled:
            try:
                items.extend(self._fetch_arxiv_ai())
            except Exception as e:
                logger.warning("ArXiv fetch failed: %s", e)

        # RSS
        for rss_url in self.config.rss_feeds:
            try:
                items.extend(self._fetch_rss(rss_url))
            except Exception as e:
                logger.warning("RSS fetch failed (%s): %s", rss_url, e)

        # 去重
        seen = set()
        unique = []
        for item in items:
            if item.id not in seen:
                seen.add(item.id)
                unique.append(item)

        # 限制数量
        unique = unique[:self.config.max_items_per_fetch]

        self._items.extend(unique)
        self._last_fetch = time.time()
        self._stats["fetched"] += len(unique)

        # 通知回调
        for item in unique:
            for cb in self._callbacks:
                try:
                    cb(item)
                except Exception:
                    pass

        return unique

    def _fetch_github_trending(self) -> List[FeedItem]:
        """获取 GitHub Trending（Python + AI 相关）"""
        import httpx

        items = []
        headers = {}
        if self.config.github_token:
            headers["Authorization"] = f"token {self.config.github_token}"

        # 搜索最近创建的 AI/Agent 相关热门项目
        try:
            resp = httpx.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": "topic:ai-agent OR topic:llm OR topic:mcp created:>2026-06-01",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 10,
                },
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for repo in data.get("items", []):
                items.append(FeedItem(
                    id=f"github_{repo['id']}",
                    title=repo.get("full_name", ""),
                    summary=repo.get("description", "")[:500],
                    source="github",
                    url=repo.get("html_url", ""),
                    published_at=repo.get("created_at", ""),
                    tags=[repo.get("language", "unknown")] + [t for t in repo.get("topics", [])[:3]],
                ))
        except Exception as e:
            logger.debug("GitHub API error: %s", e)

        return items

    def _fetch_hackernews(self) -> List[FeedItem]:
        """获取 Hacker News 热门（AI/LLM 相关）"""
        import httpx

        items = []
        try:
            # 获取 top stories
            resp = httpx.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                timeout=10,
            )
            story_ids = resp.json()[:30]

            for sid in story_ids:
                try:
                    story_resp = httpx.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                        timeout=5,
                    )
                    story = story_resp.json()
                    if not story:
                        continue

                    title = story.get("title", "")
                    # 过滤 AI 相关
                    ai_keywords = ["ai", "llm", "gpt", "agent", "claude", "gemini",
                                   "neural", "ml", "model", "inference", "mcp"]
                    if not any(kw in title.lower() for kw in ai_keywords):
                        continue

                    items.append(FeedItem(
                        id=f"hn_{sid}",
                        title=title,
                        summary=title,
                        source="hackernews",
                        url=story.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                        published_at=datetime.fromtimestamp(
                            story.get("time", 0), tz=timezone.utc
                        ).isoformat() if story.get("time") else "",
                        tags=["hackernews", "ai"],
                    ))
                except Exception:
                    continue

        except Exception as e:
            logger.debug("HN API error: %s", e)

        return items

    def _fetch_arxiv_ai(self) -> List[FeedItem]:
        """获取 ArXiv AI 论文"""
        import httpx

        items = []
        try:
            # ArXiv API 搜索 AI Agent 相关论文
            resp = httpx.get(
                "http://export.arxiv.org/api/query",
                params={
                    "search_query": "cat:cs.AI AND (agent OR LLM OR MCP)",
                    "start": 0,
                    "max_results": 5,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
                timeout=15,
            )
            # 简单解析 Atom XML
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                link = entry.find("atom:id", ns)
                published = entry.find("atom:published", ns)

                if title is not None:
                    items.append(FeedItem(
                        id=f"arxiv_{link.text.split('/')[-1] if link is not None else ''}",
                        title=title.text.strip().replace("\n", " ")[:200],
                        summary=(summary.text.strip()[:500] if summary is not None else ""),
                        source="arxiv",
                        url=link.text if link is not None else "",
                        published_at=published.text if published is not None else "",
                        tags=["arxiv", "ai-paper"],
                    ))
        except Exception as e:
            logger.debug("ArXiv API error: %s", e)

        return items

    def _fetch_rss(self, url: str) -> List[FeedItem]:
        """获取 RSS 订阅"""
        import xml.etree.ElementTree as ET

        import httpx

        items = []
        try:
            resp = httpx.get(url, timeout=10)
            root = ET.fromstring(resp.text)
            # 支持 RSS 2.0 和 Atom
            entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for entry in entries[:10]:
                title = entry.findtext("title") or entry.findtext("{http://www.w3.org/2005/Atom}title") or ""
                link = entry.findtext("link") or entry.findtext("{http://www.w3.org/2005/Atom}link") or ""
                desc = entry.findtext("description") or entry.findtext("{http://www.w3.org/2005/Atom}summary") or ""

                items.append(FeedItem(
                    id=f"rss_{hash(title + link) % 100000}",
                    title=title.strip()[:200],
                    summary=desc.strip()[:500],
                    source="rss",
                    url=link.strip(),
                    tags=["rss"],
                ))
        except Exception as e:
            logger.debug("RSS parse error (%s): %s", url, e)

        return items

    def evaluate_relevance(self, item: FeedItem, user_context: Dict[str, Any]) -> float:
        """
        评估资讯对当前用户的相关性

        使用 LLM 判断，返回 0-1 分数
        """
        # 快速规则过滤
        if not item.title:
            return 0.0

        # 基于用户技术栈的关键词匹配
        user_langs = user_context.get("languages", [])
        user_domains = user_context.get("domains", [])
        user_projects = user_context.get("current_projects", [])

        score = 0.0
        text = (item.title + " " + item.summary).lower()

        # 语言匹配
        for lang in user_langs:
            if lang.lower() in text:
                score += 0.2

        # 领域匹配
        for domain in user_domains:
            if domain.lower() in text:
                score += 0.15

        # 项目关键词匹配
        for proj in user_projects:
            words = proj.lower().split()
            for w in words:
                if len(w) > 3 and w in text:
                    score += 0.1

        # 来源质量
        if item.source == "github":
            score += 0.1
        elif item.source == "arxiv":
            score += 0.05

        return min(score, 1.0)

    def get_learned_items(self, limit: int = 50) -> List[FeedItem]:
        """获取已学习的资讯"""
        learned = [i for i in self._items if i.learned]
        return learned[-limit:]

    def get_stats(self) -> Dict[str, int]:
        return self._stats.copy()

    def mark_learned(self, item_id: str):
        for item in self._items:
            if item.id == item_id:
                item.learned = True
                self._stats["learned"] += 1
                break
