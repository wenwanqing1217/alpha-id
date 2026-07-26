"""
Alpha-ID 记忆存储 —— 孪生大脑的本地记忆模块

替代旧的 Coze Knowledge 依赖，使用本地存储（JSON 文件 / PostgreSQL）。
V1 支持关键词搜索，V2 使用 ChromaDB 向量嵌入语义搜索。

记忆按 sensitivity（敏感度 0-100）分级，配合可见度模型使用。
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.settings import settings
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
                str(settings.coze_workspace), "assets", f"memory_{alpha_id.replace('-', '_')}.json"
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
            self._vector_index.add(
                memory.memory_id, content, tags or [],
                metadata={"category": memory.category, "sensitivity": memory.sensitivity},
            )

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


class _SimpleEmbeddingFunction:
    """轻量级嵌入函数——基于字符 n-gram 的哈希 TF 向量化，无需下载外部模型。

    使用固定哈希映射将 n-gram 投影到 512 维空间（无状态设计），
    保证文档嵌入和查询嵌入使用完全相同的算法，支持余弦相似度匹配。
    """

    def __init__(self, ngram_range=(2, 4), dim: int = 512):
        self.ngram_range = ngram_range
        self.dim = dim

    def name(self) -> str:
        return "simple_ngram_tf"

    def _tokenize(self, text: str) -> List[str]:
        ngrams = []
        min_n, max_n = self.ngram_range
        text_len = len(text)
        for n in range(min_n, min(max_n, text_len) + 1):
            for i in range(text_len - n + 1):
                ngrams.append(text[i : i + n])
        return ngrams

    def _ngram_to_dim(self, ngram: str) -> int:
        import hashlib

        h = hashlib.md5(ngram.encode("utf-8")).digest()
        return int.from_bytes(h[:4], "big") % self.dim

    def _embed(self, text: str) -> List[float]:
        import math

        ngrams = self._tokenize(text)
        if not ngrams:
            return [0.0] * self.dim
        total = len(ngrams)
        tf: Dict[str, int] = {}
        for ng in ngrams:
            tf[ng] = tf.get(ng, 0) + 1
        vec = [0.0] * self.dim
        for ng, count in tf.items():
            dim = self._ngram_to_dim(ng)
            vec[dim] = count / total
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_documents(self, input: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in input]

    def embed_query(self, input: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in input]

    def __call__(self, input: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in input]


class VectorMemoryIndex:
    """
    向量记忆索引 —— 基于 ChromaDB 的语义搜索。

    使用 ChromaDB 嵌入式模式（无需服务端）。
    默认使用轻量级嵌入函数（无需下载外部模型），
    可配置为真实语义嵌入（需预下载 ONNX 模型）。
    """

    def __init__(
        self,
        alpha_id: str,
        persist_dir: Optional[str] = None,
        top_k: int = 50,
        min_similarity: float = 0.1,
        use_native_embedding: bool = False,
    ):
        self.alpha_id = alpha_id
        self.top_k = top_k
        self.min_similarity = min_similarity
        self._client = None
        self._collection = None

        if persist_dir is None:
            persist_dir = str(Path.home() / ".alpha-id" / "chroma" / alpha_id.replace("-", "_"))

        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )

            embedding_fn = None
            if use_native_embedding:
                try:
                    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
                    embedding_fn = ONNXMiniLM_L6_V2()
                except Exception:
                    pass

            if embedding_fn is None:
                embedding_fn = _SimpleEmbeddingFunction()

            self._collection = self._client.get_or_create_collection(
                name=f"memory_{alpha_id.replace('-', '_')}",
                metadata={"hnsw:space": "cosine"},
                embedding_function=embedding_fn,
            )
        except ImportError:
            self._client = None
            self._collection = None
        except Exception:
            self._client = None
            self._collection = None

    @property
    def is_available(self) -> bool:
        return self._collection is not None

    def add(self, memory_id: str, content: str, tags: List[str], metadata: Optional[Dict[str, Any]] = None) -> None:
        if not self.is_available:
            return
        doc = content + " " + " ".join(tags)
        meta = metadata or {}
        meta["tags"] = ",".join(tags) if tags else ""
        try:
            self._collection.upsert(
                ids=[memory_id],
                documents=[doc],
                metadatas=[meta],
            )
        except Exception:
            pass

    def remove(self, memory_id: str) -> None:
        if not self.is_available:
            return
        try:
            self._collection.delete(ids=[memory_id])
        except Exception:
            pass

    def build_index(self, memories: Dict[str, Any]) -> None:
        if not self.is_available:
            return
        ids = []
        docs = []
        metadatas = []
        for mid, mem in memories.items():
            ids.append(mid)
            content = mem.get("content", "")
            tags = mem.get("tags", [])
            cat = mem.get("category", "")
            sens = mem.get("sensitivity", 0)
            doc = content + " " + " ".join(tags)
            metadatas.append({"tags": ",".join(tags) if tags else "", "category": cat, "sensitivity": sens})
            docs.append(doc)
        if ids:
            try:
                self._collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
            except Exception:
                pass

    def search(
        self,
        query: str,
        memories: Dict[str, Any],
        min_similarity: Optional[float] = None,
        category: Optional[str] = None,
        max_sensitivity: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        threshold = min_similarity if min_similarity is not None else self.min_similarity
        if not query or not self.is_available:
            return []
        try:
            count = self._collection.count()
            if count == 0:
                return []

            where_filter = {}
            if category:
                where_filter["category"] = category
            if max_sensitivity is not None:
                where_filter["sensitivity"] = {"$lte": max_sensitivity}

            query_kwargs = {
                "query_texts": [query],
                "n_results": min(self.top_k, count),
                "include": ["distances", "metadatas"],
            }
            if where_filter:
                query_kwargs["where"] = where_filter

            results = self._collection.query(**query_kwargs)
        except Exception:
            return []

        if not results or not results["ids"] or not results["ids"][0]:
            return []

        ids = results["ids"][0]
        distances = results.get("distances", [[]])[0] if results.get("distances") else []

        scored = []
        for i, mid in enumerate(ids):
            dist = distances[i] if i < len(distances) else 1.0
            sim = 1.0 - dist
            if sim >= threshold:
                scored.append((sim, mid))

        scored.sort(key=lambda x: x[0], reverse=True)
        candidates = scored[: self.top_k]

        output = []
        for sim, mid in candidates:
            mem = memories.get(mid)
            if mem:
                result = dict(mem)
                result["score"] = round(sim, 6)
                output.append(result)
        return output

    def hybrid_search(
        self,
        query: str,
        memories: Dict[str, Any],
        min_similarity: Optional[float] = None,
        keyword_weight: float = 0.3,
        vector_weight: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """混合搜索：关键词匹配 + 向量语义"""
        vector_results = self.search(query, memories, min_similarity)
        keyword_results = self._keyword_search(query, memories)

        scores: Dict[str, float] = {}
        for r in vector_results:
            mid = r.get("memory_id", "")
            scores[mid] = scores.get(mid, 0.0) + vector_weight * r.get("score", 0.0)
        for r in keyword_results:
            mid = r.get("memory_id", "")
            scores[mid] = scores.get(mid, 0.0) + keyword_weight * r.get("_keyword_score", 0.0)

        sorted_ids = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        output = []
        for mid in sorted_ids[: self.top_k]:
            mem = memories.get(mid)
            if mem:
                result = dict(mem)
                result["score"] = round(scores[mid], 6)
                output.append(result)
        return output

    def _keyword_search(self, query: str, memories: Dict[str, Any]) -> List[Dict[str, Any]]:
        """关键词匹配搜索（轻量补充）"""
        query_lower = query.lower()
        results = []
        for mid, mem in memories.items():
            content = mem.get("content", "").lower()
            tags = " ".join(mem.get("tags", [])).lower()
            cat = mem.get("category", "").lower()

            score = 0.0
            if query_lower in content:
                score += 0.8
            if query_lower in tags:
                score += 0.6
            if query_lower in cat:
                score += 0.4

            if score > 0:
                result = dict(mem)
                result["_keyword_score"] = score
                results.append(result)

        results.sort(key=lambda x: x.get("_keyword_score", 0), reverse=True)
        return results[: self.top_k]

    def optimize(self) -> None:
        """优化索引：压缩存储、重建 HNSW 索引"""
        if not self.is_available:
            return
        try:
            count = self._collection.count()
            if count > 0:
                self._collection.upsert(
                    ids=self._collection.get()["ids"],
                    documents=self._collection.get()["documents"],
                    metadatas=self._collection.get()["metadatas"],
                )
        except Exception:
            pass
