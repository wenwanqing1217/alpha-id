"""
Alpha-ID 记忆存储 —— 孪生大脑的本地记忆模块

替代旧的 Coze Knowledge 依赖，使用本地存储（JSON 文件 / PostgreSQL）。
V1 支持关键词搜索，V2 升级向量搜索。

记忆按 sensitivity（敏感度 0-100）分级，配合可见度模型使用。
"""

import math
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.storage import JsonStorage, StorageBackend


@dataclass
class AlphaMemory:
    """一条记忆"""

    memory_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    alpha_id: str = ""  # 属于哪个 Alpha-ID
    content: str = ""  # 记忆内容
    category: str = "general"  # 分类：experience/preference/knowledge/social/general
    sensitivity: int = 0  # 敏感度 0-100（0=公开，100=绝密）
    source: str = "self"  # 来源：self/social/system
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
        self._vector_index = None

        if storage is None:
            import os

            db_path = os.path.join(
                os.getenv("COZE_WORKSPACE_PATH", os.getcwd()), "assets", f"memory_{alpha_id.replace('-', '_')}.json"
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

    def save(
        self,
        content: str,
        category: str = "general",
        sensitivity: int = 0,
        source: str = "self",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
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

        # 更新向量索引（如果已存在）
        if self._vector_index is not None:
            self._vector_index.add(memory.memory_id, content, tags or [])

        return {"success": True, "memory_id": memory.memory_id, "message": "记忆已保存"}

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """获取单条记忆"""
        memories = self._storage.load(self.alpha_id) or {}
        return memories.get(memory_id)

    def query(
        self, keyword: str = "", category: str = "", max_sensitivity: int = 100, limit: int = 20, query_text: str = ""
    ) -> List[Dict[str, Any]]:
        """
        查询记忆。

        V1 关键词搜索（大小写不敏感）。
        V2 语义搜索（当 query_text 非空时自动启用）。

        Args:
            keyword: 关键词（空字符串返回全部）
            category: 分类过滤（空字符串不过滤）
            max_sensitivity: 最大敏感度（可见度过滤用）
            limit: 最大返回条数
            query_text: 语义查询文本（非空时启用向量搜索）

        Returns:
            符合条件的记忆列表
        """
        memories = self._storage.load(self.alpha_id) or {}

        # V2: 语义搜索
        if query_text:
            # 延迟创建向量索引
            if self._vector_index is None:
                self._vector_index = VectorMemoryIndex(self.alpha_id)
                self._vector_index.build_index(memories)

            results = self._vector_index.search(query_text, memories)

            # 应用分类和敏感度过滤
            filtered = []
            for mem in results:
                if mem.get("sensitivity", 0) > max_sensitivity:
                    continue
                if category and mem.get("category") != category:
                    continue
                filtered.append(mem)

            return filtered[:limit]

        # V1: 关键词搜索（原有逻辑不变）
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

    def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        category: Optional[str] = None,
        sensitivity: Optional[int] = None,
        source: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """更新一条已有记忆。只更新提供的字段，未提供的字段保持不变。

        Args:
            memory_id: 要更新的记忆 ID
            content: 新内容（None 表示不更新）
            category: 新分类
            sensitivity: 新敏感度
            source: 新来源
            tags: 新标签列表

        Returns:
            更新结果，包含更新后的记忆
        """
        memories = self._storage.load(self.alpha_id) or {}
        if memory_id not in memories:
            return {"success": False, "message": "记忆不存在"}

        mem = memories[memory_id]
        if content is not None:
            mem["content"] = content
        if category is not None:
            mem["category"] = category
        if sensitivity is not None:
            mem["sensitivity"] = max(0, min(100, sensitivity))
        if source is not None:
            mem["source"] = source
        if tags is not None:
            mem["tags"] = tags

        mem["timestamp"] = datetime.now().timestamp()
        memories[memory_id] = mem
        self._storage.save(self.alpha_id, memories)

        # 更新向量索引
        if self._vector_index is not None:
            self._vector_index.remove(memory_id)
            self._vector_index.add(memory_id, mem["content"], mem.get("tags", []))

        return {"success": True, "memory_id": memory_id, "message": "记忆已更新"}

    def list_by_sensitivity(self, max_sensitivity: int = 100) -> List[Dict[str, Any]]:
        """
        按敏感度列出记忆（用于可见度控制）。
        """
        memories = self._storage.load(self.alpha_id) or {}
        return [mem for mem in memories.values() if mem.get("sensitivity", 0) <= max_sensitivity]

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


class VectorMemoryIndex:
    """
    向量记忆索引 —— 字符 n-gram TF-IDF + 余弦相似度语义搜索。

    纯 Python 实现，无需外部依赖。用于 V2 记忆搜索升级。
    """

    def __init__(self, alpha_id: str, ngram_range: tuple = (2, 4), top_k: int = 50):
        self.alpha_id = alpha_id
        self.ngram_range = ngram_range  # (min_n, max_n)
        self.top_k = top_k
        self._doc_freq: Dict[str, int] = defaultdict(int)  # n-gram -> 文档频率
        self._vectors: Dict[str, Dict[str, float]] = {}  # memory_id -> TF-IDF 向量
        self._total_docs: int = 0

    # ── 内部方法 ──

    def _tokenize(self, text: str) -> List[str]:
        """
        提取字符 n-gram。
        例如 "hello" 且 ngram_range=(2,4) 返回：
        "he","el","ll","lo","hel","ell","llo","hell","ello"
        """
        ngrams = []
        min_n, max_n = self.ngram_range
        text_len = len(text)
        for n in range(min_n, min(max_n, text_len) + 1):
            for i in range(text_len - n + 1):
                ngrams.append(text[i : i + n])
        return ngrams

    def _tfidf(self, ngrams: List[str]) -> Dict[str, float]:
        """
        从 n-gram 列表计算 TF-IDF 向量。

        TF = 词频 / 总 n-gram 数
        IDF = log(1 + total_docs / (1 + doc_freq))

        公式保证 IDF > 0 即使只有一个文档。
        """
        if not ngrams:
            return {}

        total_ngrams = len(ngrams)
        tf_raw: Dict[str, int] = defaultdict(int)
        for ng in ngrams:
            tf_raw[ng] += 1

        result: Dict[str, float] = {}
        for ng, count in tf_raw.items():
            tf = count / total_ngrams
            idf = math.log(1 + (self._total_docs) / (1 + self._doc_freq.get(ng, 0)))
            result[ng] = tf * idf

        return result

    def _cosine_sim(self, v1: Dict[str, float], v2: Dict[str, float]) -> float:
        """计算两个稀疏向量的余弦相似度。"""
        # 点积
        dot = 0.0
        for key in v1:
            if key in v2:
                dot += v1[key] * v2[key]

        # 模长
        norm1 = math.sqrt(sum(v * v for v in v1.values()))
        norm2 = math.sqrt(sum(v * v for v in v2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot / (norm1 * norm2)

    # ── 索引方法 ──

    def add(self, memory_id: str, content: str, tags: List[str]) -> None:
        """索引一条记忆的内容和标签。"""
        text = content + " " + " ".join(tags)
        ngrams = self._tokenize(text)

        # 更新文档频率
        seen = set(ngrams)
        for ng in seen:
            self._doc_freq[ng] += 1
        self._total_docs += 1

        # 计算并缓存向量
        self._vectors[memory_id] = self._tfidf(ngrams)

    def remove(self, memory_id: str) -> None:
        """从索引中移除一条记忆。"""
        if memory_id in self._vectors:
            del self._vectors[memory_id]

    def build_index(self, memories: Dict[str, Any]) -> None:
        """从所有记忆重建完整索引。"""
        self._doc_freq.clear()
        self._vectors.clear()
        self._total_docs = 0

        for mid, mem in memories.items():
            content = mem.get("content", "")
            tags = mem.get("tags", [])
            self.add(mid, content, tags)

    def search(self, query: str, memories: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        语义搜索记忆。

        1. 对查询文本提取 n-gram 并计算 TF-IDF 向量
        2. 对每个已索引记忆计算余弦相似度
        3. 取 top_k 候选并按相似度降序排序
        4. 从原始 memories dict 中获取完整数据并附加 score

        Returns:
            带 score 的记忆列表（不修改原始 dict）
        """
        if not query or not self._vectors:
            return []

        # 将查询视为一个文档来计算 TF-IDF
        query_ngrams = self._tokenize(query)
        if not query_ngrams:
            return []

        # 查询的 TF（无 IDF — 查询本身不改变文档频率）
        total_q = len(query_ngrams)
        tf_raw: Dict[str, int] = defaultdict(int)
        for ng in query_ngrams:
            tf_raw[ng] += 1

        query_vec: Dict[str, float] = {}
        for ng, count in tf_raw.items():
            tf = count / total_q
            idf = math.log(1 + (self._total_docs) / (1 + self._doc_freq.get(ng, 0)))
            query_vec[ng] = tf * idf

        # 计算相似度
        scored: List[tuple[float, str]] = []
        for mid, vec in self._vectors.items():
            sim = self._cosine_sim(query_vec, vec)
            if sim > 0:
                scored.append((sim, mid))

        # 取 top_k 候选，按相似度降序
        scored.sort(key=lambda x: x[0], reverse=True)
        candidates = scored[: self.top_k]

        # 组装结果（不修改原始 dict）
        results = []
        for sim, mid in candidates:
            mem = memories.get(mid)
            if mem:
                result = dict(mem)
                result["score"] = round(sim, 6)
                results.append(result)

        return results
