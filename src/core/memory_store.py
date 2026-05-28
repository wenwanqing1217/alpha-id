"""
Alpha-ID 记忆存储 —— 孪生大脑的本地记忆模块

替代旧的 Coze Knowledge 依赖，使用本地存储（JSON 文件 / PostgreSQL）。
V1 支持关键词搜索，V2 升级向量搜索。

记忆按 sensitivity（敏感度 0-100）分级，配合可见度模型使用。
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.storage import JsonStorage, StorageBackend


@dataclass
class AlphaMemory:
    """一条记忆"""
    memory_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    alpha_id: str = ""               # 属于哪个 Alpha-ID
    content: str = ""                # 记忆内容
    category: str = "general"        # 分类：experience/preference/knowledge/social/general
    sensitivity: int = 0             # 敏感度 0-100（0=公开，100=绝密）
    source: str = "self"             # 来源：self/social/system
    tags: List[str] = field(default_factory=list)  # 标签，用于快速检索
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())


class MemoryStore:
    """
    记忆存储器 —— 管理一个 Alpha-ID 的所有记忆。

    V1 实现：JSON 文件 + 关键词匹配
    V2 计划：向量嵌入 + 语义搜索（Chroma/FAISS）
    """

    def __init__(self, alpha_id: str, storage: Optional[StorageBackend] = None):
        self.alpha_id = alpha_id

        if storage is None:
            import os
            db_path = os.path.join(
                os.getenv("COZE_WORKSPACE_PATH", os.getcwd()),
                "assets",
                f"memory_{alpha_id.replace('-', '_')}.json"
            )
            self._storage = JsonStorage(db_path)
        else:
            self._storage = storage

        self._init_store()

    def _init_store(self):
        """初始化存储结构"""
        memories = self._storage.load(self.alpha_id)
        if memories is None:
            self._storage.save(self.alpha_id, {})

    # ── 核心方法 ──

    def save(self, content: str, category: str = "general",
             sensitivity: int = 0, source: str = "self",
             tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        保存一条记忆。

        Args:
            content: 记忆内容
            category: 分类
            sensitivity: 敏感度 0-100
            source: 记忆来源
            tags: 标签列表

        Returns:
            保存结果，包含 memory_id
        """
        memory = AlphaMemory(
            alpha_id=self.alpha_id,
            content=content,
            category=category,
            sensitivity=max(0, min(100, sensitivity)),
            source=source,
            tags=tags or [],
        )

        memories = self._storage.load(self.alpha_id) or {}
        memories[memory.memory_id] = asdict(memory)
        self._storage.save(self.alpha_id, memories)

        return {"success": True, "memory_id": memory.memory_id, "message": "记忆已保存"}

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """获取单条记忆"""
        memories = self._storage.load(self.alpha_id) or {}
        return memories.get(memory_id)

    def query(self, keyword: str = "", category: str = "",
              max_sensitivity: int = 100, limit: int = 20) -> List[Dict[str, Any]]:
        """
        查询记忆。

        V1 关键词搜索（大小写不敏感）。
        V2 会升级为向量语义搜索。

        Args:
            keyword: 关键词（空字符串返回全部）
            category: 分类过滤（空字符串不过滤）
            max_sensitivity: 最大敏感度（可见度过滤用）
            limit: 最大返回条数

        Returns:
            符合条件的记忆列表
        """
        memories = self._storage.load(self.alpha_id) or {}
        results = []

        for mem in memories.values():
            # 敏感度过滤
            if mem.get("sensitivity", 0) > max_sensitivity:
                continue

            # 分类过滤
            if category and mem.get("category") != category:
                continue

            # 关键词搜索
            if keyword:
                kw = keyword.lower()
                content = mem.get("content", "").lower()
                tag_text = " ".join(mem.get("tags", [])).lower()
                if kw not in content and kw not in tag_text:
                    continue

            results.append(mem)

        # 按时间倒序
        results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return results[:limit]

    def delete(self, memory_id: str) -> Dict[str, Any]:
        """删除一条记忆"""
        memories = self._storage.load(self.alpha_id) or {}
        if memory_id in memories:
            del memories[memory_id]
            self._storage.save(self.alpha_id, memories)
            return {"success": True, "message": "记忆已删除"}
        return {"success": False, "message": "记忆不存在"}

    def list_by_sensitivity(self, max_sensitivity: int = 100) -> List[Dict[str, Any]]:
        """
        按敏感度列出记忆（用于可见度控制）。
        """
        memories = self._storage.load(self.alpha_id) or {}
        return [
            mem for mem in memories.values()
            if mem.get("sensitivity", 0) <= max_sensitivity
        ]

    def count(self, category: str = "") -> int:
        """统计记忆数量"""
        memories = self._storage.load(self.alpha_id) or {}
        if category:
            return sum(1 for m in memories.values() if m.get("category") == category)
        return len(memories)

    def clear(self) -> Dict[str, Any]:
        """清空所有记忆"""
        self._storage.save(self.alpha_id, {})
        return {"success": True, "message": "所有记忆已清空"}
