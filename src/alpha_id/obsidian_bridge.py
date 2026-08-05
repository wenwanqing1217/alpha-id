"""
Alpha-ID Obsidian Bridge — Obsidian 双向同步
=============================================

打通 Obsidian 与 Alpha-ID 的闭环：
  - 写入：Agent 生成笔记 → 写入 Obsidian
  - 读取：用户修改笔记 → Alpha-ID 学习
  - 关联：笔记之间自动建立双向链接
  - 沉淀：积累够了自动生成总结笔记

核心洞察：
  Obsidian 不是终点，是对话的起点。
  用户在笔记上改的每一个字，都是对 Alpha-ID 的反馈。
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class NoteEvent:
    """笔记变更事件"""
    note_path: str = ""
    note_title: str = ""
    action: str = ""          # created / modified / deleted
    content: str = ""
    diff: str = ""            # 修改的差异
    tags: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)  # [[双向链接]]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ObsidianBridge:
    """
    Obsidian 桥接器

    用法：
        bridge = ObsidianBridge(vault_path="/path/to/vault")
        bridge.write_note("项目/Alpha-ID", "# Alpha-ID\\n内容...")
        bridge.on_change(handle_note_change)
        bridge.scan_changes()
    """

    def __init__(self, vault_path: str):
        self._vault = Path(vault_path)
        self._file_states: Dict[str, float] = {}  # path -> mtime
        self._callbacks: List[Callable[[NoteEvent], None]] = []
        self._stats = {"written": 0, "read": 0, "linked": 0}

        if not self._vault.exists():
            logger.warning("Obsidian vault 不存在: %s", vault_path)
        else:
            self._init_file_states()

    def _init_file_states(self):
        """初始化文件状态"""
        if self._vault.exists():
            for f in self._vault.rglob("*.md"):
                self._file_states[str(f)] = f.stat().st_mtime

    def on_change(self, callback: Callable[[NoteEvent], None]):
        """注册笔记变更回调"""
        self._callbacks.append(callback)

    # ── 写入 Obsidian ──

    def write_note(self, title: str, content: str, folder: str = "",
                   tags: List[str] = None, links: List[str] = None) -> str:
        """
        写入笔记到 Obsidian

        Args:
            title: 笔记标题（不含 .md）
            content: Markdown 内容
            folder: 子文件夹路径（可选）
            tags: 标签列表
            links: 双向链接列表

        Returns:
            写入的文件路径
        """
        if not self._vault.exists():
            logger.warning("Vault 不存在，无法写入")
            return ""

        # 确定路径
        if folder:
            note_dir = self._vault / folder
            note_dir.mkdir(parents=True, exist_ok=True)
        else:
            note_dir = self._vault

        # 清理文件名
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
        note_path = note_dir / f"{safe_title}.md"

        # 构建完整内容（含 frontmatter）
        full_content = self._build_note_content(content, tags, links)

        # 写入
        note_path.write_text(full_content, encoding="utf-8")
        self._file_states[str(note_path)] = note_path.stat().st_mtime
        self._stats["written"] += 1

        logger.info("写入 Obsidian 笔记: %s", note_path.relative_to(self._vault))
        return str(note_path)

    def _build_note_content(self, content: str, tags: List[str] = None,
                            links: List[str] = None) -> str:
        """构建完整笔记内容"""
        parts = []

        # Frontmatter
        frontmatter = {"created": datetime.now(timezone.utc).isoformat()}
        if tags:
            frontmatter["tags"] = tags
        if links:
            frontmatter["links"] = links
        parts.append("---")
        parts.append(json.dumps(frontmatter, ensure_ascii=False, indent=2))
        parts.append("---")
        parts.append("")

        # 内容
        parts.append(content)

        # 相关链接
        if links:
            parts.append("")
            parts.append("## 相关链接")
            for link in links:
                parts.append(f"- [[{link}]]")

        return "\n".join(parts)

    def append_to_note(self, title: str, new_content: str):
        """追加内容到现有笔记"""
        note_path = self._find_note(title)
        if not note_path:
            return self.write_note(title, new_content)

        existing = note_path.read_text(encoding="utf-8")
        updated = existing + "\n\n" + new_content
        note_path.write_text(updated, encoding="utf-8")
        self._file_states[str(note_path)] = note_path.stat().st_mtime
        self._stats["written"] += 1

    # ── 读取 Obsidian ──

    def scan_changes(self) -> List[NoteEvent]:
        """扫描笔记变更"""
        events: List[NoteEvent] = []

        if not self._vault.exists():
            return events

        current_files = {}
        for f in self._vault.rglob("*.md"):
            if f.is_file():
                current_files[str(f)] = f.stat().st_mtime

        # 新增
        for path, mtime in current_files.items():
            if path not in self._file_states:
                event = self._parse_note_event(path, "created")
                events.append(event)

        # 修改
        for path, mtime in current_files.items():
            if path in self._file_states and mtime > self._file_states[path]:
                event = self._parse_note_event(path, "modified")
                events.append(event)

        # 删除
        for path in self._file_states:
            if path not in current_files:
                events.append(NoteEvent(
                    note_path=path,
                    action="deleted",
                ))

        # 更新状态
        self._file_states = current_files
        self._stats["read"] += len(events)

        # 通知回调
        for event in events:
            for cb in self._callbacks:
                try:
                    cb(event)
                except Exception:
                    pass

        return events

    def _parse_note_event(self, path: str, action: str) -> NoteEvent:
        """解析笔记内容"""
        p = Path(path)
        content = ""
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            pass

        # 提取标签 (#tag)
        tags = re.findall(r'#([a-zA-Z0-9_/-]+)', content)

        # 提取双向链接 ([[link]])
        links = re.findall(r'\[\[([^\]]+)\]\]', content)

        return NoteEvent(
            note_path=path,
            note_title=p.stem,
            action=action,
            content=content[:2000],
            tags=tags,
            links=links,
        )

    def _find_note(self, title: str) -> Optional[Path]:
        """根据标题查找笔记"""
        for f in self._vault.rglob("*.md"):
            if f.stem == title:
                return f
        return None

    # ── 智能关联 ──

    def auto_link(self, note_path: str, related_titles: List[str]):
        """为笔记添加双向链接"""
        p = Path(note_path)
        if not p.exists():
            return

        content = p.read_text(encoding="utf-8")

        # 检查是否已有这些链接
        existing_links = set(re.findall(r'\[\[([^\]]+)\]\]', content))
        new_links = [t for t in related_titles if t not in existing_links]

        if new_links:
            link_section = "\n".join(f"[[{link}]]" for link in new_links)
            updated = content + "\n\n## 自动关联\n" + link_section
            p.write_text(updated, encoding="utf-8")
            self._stats["linked"] += 1

    def search_notes(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索笔记内容"""
        results = []
        if not self._vault.exists():
            return results

        for f in self._vault.rglob("*.md"):
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8")
                if query.lower() in content.lower():
                    results.append({
                        "title": f.stem,
                        "path": str(f.relative_to(self._vault)),
                        "snippet": self._extract_snippet(content, query),
                    })
            except Exception:
                continue

        return results[:limit]

    def _extract_snippet(self, content: str, query: str, context: int = 50) -> str:
        """提取关键词周围的文本"""
        idx = content.lower().find(query.lower())
        if idx == -1:
            return content[:100]
        start = max(0, idx - context)
        end = min(len(content), idx + len(query) + context)
        return content[start:end]

    # ── 沉淀 ──

    def find_notes_for_sedimentation(self, min_notes: int = 3) -> Dict[str, List[str]]:
        """
        查找可以沉淀的笔记组（同一主题的多个笔记）

        Returns:
            {主题: [笔记路径列表]}
        """
        tag_groups: Dict[str, List[str]] = {}

        if not self._vault.exists():
            return tag_groups

        for f in self._vault.rglob("*.md"):
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8")
                tags = re.findall(r'#([a-zA-Z0-9_/-]+)', content)
                for tag in tags:
                    tag_groups.setdefault(tag, []).append(str(f))
            except Exception:
                continue

        # 只返回有足够笔记的主题
        return {tag: paths for tag, paths in tag_groups.items() if len(paths) >= min_notes}

    def get_stats(self) -> Dict[str, int]:
        return self._stats.copy()
