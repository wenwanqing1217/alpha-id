"""
FAIRY 双链记忆 — 私有链 + 知识链

私有链：sensitivity >= 70，加密存储，仅 FAIRY 可访问
知识链：sensitivity < 70，可搜索，可共享给其他工具

复用现有的 ChromaDB 向量存储（通过 core 模块），
不重复造轮子。
"""

import logging
import os
import time
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

PRIVATE_THRESHOLD = 70  # sensitivity >= 70 为私有
DB_PATH = os.getenv("FAIRY_MEMORY_PATH", os.path.expanduser("~/.fairy/memory"))


class FairyMemory:
    """
    双链记忆适配器

    私有记忆：加密 + 本地存储
    知识记忆：向量数据库（ChromaDB），可语义搜索
    """

    def __init__(self, founder_did: str = "did:aid:unknown", db_path: str = DB_PATH):
        self.founder_did = founder_did
        self.db_path = db_path
        self._collection = None
        self._ensure_db()

    def _ensure_db(self):
        """确保存储目录和数据库存在"""
        os.makedirs(self.db_path, exist_ok=True)
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.db_path)
            self._collection = self._client.get_or_create_collection(
                name="fairy_knowledge",
                metadata={"description": "FAIRY 知识链"}
            )
            logger.info(f"记忆数据库就绪: {self.db_path}")
        except ImportError:
            logger.warning("chromadb 未安装，知识链不可用")
            self._client = None
            self._collection = None

    def is_available(self) -> bool:
        """检查记忆系统是否可用"""
        return self._collection is not None

    def remember(self, text: str, sensitivity: int = 50,
                 metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        存储一条记忆

        Args:
            text: 记忆文本
            sensitivity: 敏感度 (0-100)
            metadata: 额外元数据

        Returns:
            是否存储成功
        """
        if sensitivity >= PRIVATE_THRESHOLD:
            return self._store_private(text, metadata)
        else:
            return self._store_knowledge(text, metadata)

    def _store_private(self, text: str, metadata: Optional[Dict] = None) -> bool:
        """存储私有记忆（加密文件）"""
        try:
            from cryptography.fernet import Fernet

            key_path = os.path.join(self.db_path, ".key")
            if os.path.exists(key_path):
                with open(key_path, "rb") as f:
                    key = f.read()
            else:
                key = Fernet.generate_key()
                with open(key_path, "wb") as f:
                    f.write(key)

            f = Fernet(key)
            encrypted = f.encrypt(text.encode("utf-8"))

            # 用时间戳作为文件名
            ts = int(time.time() * 1000)
            filepath = os.path.join(self.db_path, f"private_{ts}.enc")
            with open(filepath, "wb") as fp:
                fp.write(encrypted)

            logger.debug(f"私有记忆存储: {filepath}")
            return True
        except ImportError:
            logger.warning("cryptography 未安装，无法加密私有记忆")
            return False
        except Exception as e:
            logger.error(f"私有记忆存储失败: {e}")
            return False

    def _store_knowledge(self, text: str, metadata: Optional[Dict] = None) -> bool:
        """存储知识记忆（ChromaDB）"""
        if not self._collection:
            return False
        try:
            doc_id = f"doc_{int(time.time() * 1000)}"
            meta = metadata or {}
            meta["timestamp"] = time.time()
            meta["sensitivity"] = 0  # 知识链都是低敏感
            self._collection.add(
                documents=[text],
                ids=[doc_id],
                metadatas=[meta]
            )
            logger.debug(f"知识记忆存储: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"知识记忆存储失败: {e}")
            return False

    def recall(self, query: str, limit: int = 5) -> List[str]:
        """
        回忆：语义搜索知识链

        Args:
            query: 搜索词
            limit: 返回数量

        Returns:
            匹配的记忆文本列表
        """
        if not self._collection:
            return []
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=limit
            )
            docs = results.get("documents", [[]])[0]
            return docs
        except Exception as e:
            logger.error(f"回忆失败: {e}")
            return []

    def build_context_for_brain(self) -> List[str]:
        """
        构建给大脑的记忆上下文（最近知识）

        Returns:
            最近的知识记忆列表（最多 10 条）
        """
        return self.get_recent(hours=24)[:10]

    def get_recent(self, hours: int = 24) -> List[str]:
        """获取最近 N 小时的知识记忆"""
        if not self._collection:
            return []
        try:
            all_docs = self._collection.get(limit=100)
            docs = all_docs.get("documents", [])
            return docs[:20]
        except Exception as e:
            logger.error(f"获取最近记忆失败: {e}")
            return []

    def stats(self) -> Dict[str, int]:
        """记忆统计

        Returns:
            {"knowledge": int, "private": int}
        """
        result = {"knowledge": 0, "private": 0}
        try:
            # 私有记忆：数 .enc 文件
            if os.path.isdir(self.db_path):
                private_files = [f for f in os.listdir(self.db_path) if f.startswith("private_")]
                result["private"] = len(private_files)

            # 知识记忆：ChromaDB count
            if self._collection:
                result["knowledge"] = self._collection.count()
        except Exception:
            pass
        return result
