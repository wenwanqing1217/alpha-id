"""
SQLite 存储后端（SQLAlchemy 实现）

完全替换 JsonStorage 作为默认存储后端。
零外部依赖——SQLite 是 Python 标准库的一部分。
支持事务、并发读、索引查询。
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from core.storage import StorageBackend


class SqliteStorage(StorageBackend):
    """SQLite 存储后端（线程安全，WAL 模式）"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(
                os.getenv("COZE_WORKSPACE_PATH", os.getcwd()),
                "assets",
                "alpha_id.db",
            )
        self.db_path = db_path
        self._local = threading.local()  # 每个线程一个连接

        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_schema()

    # ── 连接管理 ──

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的连接（自动创建）"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _tx(self):
        """事务上下文（自动提交/回滚）"""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self):
        """关闭当前线程的连接"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

    # ── 建表 ──

    def _init_schema(self):
        """初始化数据库 schema"""
        schema = """
        CREATE TABLE IF NOT EXISTS collections (
            collection_name TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL DEFAULT '_default',
            data TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_collections_name ON collections(collection_name);

        CREATE TABLE IF NOT EXISTS users (
            alpha_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS social_friends (
            alpha_id TEXT NOT NULL,
            friend_id TEXT NOT NULL,
            PRIMARY KEY (alpha_id, friend_id)
        );
        CREATE INDEX IF NOT EXISTS idx_friends_alpha ON social_friends(alpha_id);

        CREATE TABLE IF NOT EXISTS social_requests (
            request_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_requests_to ON social_requests(
            json_extract(data, '$.to_alpha_id')
        );

        CREATE TABLE IF NOT EXISTS social_messages (
            message_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_to ON social_messages(
            json_extract(data, '$.to_alpha_id')
        );
        """
        with self._tx() as conn:
            conn.executescript(schema)

    # ── StorageBackend 接口实现 ──

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载整个集合（兼容旧 JSON 的 load/save 模式）"""
        with self._tx() as conn:
            row = conn.execute(
                "SELECT data FROM collections WHERE collection_name = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            return json.loads(row["data"])

    def save(self, key: str, data: Dict[str, Any]):
        """保存整个集合"""
        with self._tx() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO collections (collection_name, doc_id, data)
                   VALUES (?, '_default', ?)""",
                (key, json.dumps(data, ensure_ascii=False)),
            )

    def get(self, collection: str, record_id: str) -> Optional[Dict[str, Any]]:
        """获取单条记录"""
        with self._tx() as conn:
            row = conn.execute(
                "SELECT data FROM collections WHERE collection_name = ?",
                (f"{collection}_item_{record_id}",),
            ).fetchone()
            if row is None:
                return None
            return json.loads(row["data"])

    def put(self, collection: str, record_id: str, record: Dict[str, Any]):
        """写入单条记录"""
        with self._tx() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO collections (collection_name, doc_id, data)
                   VALUES (?, '_default', ?)""",
                (f"{collection}_item_{record_id}", json.dumps(record, ensure_ascii=False)),
            )

    def delete(self, collection: str, record_id: str):
        """删除单条记录"""
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM collections WHERE collection_name = ?",
                (f"{collection}_item_{record_id}",),
            )

    def list(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """列出集合中的记录，支持按字段过滤"""
        # 加载整个集合做过滤（对于小规模数据够用）
        data = self.load(collection)
        if data is None:
            return []
        items = list(data.values())
        if filters:
            items = [item for item in items if all(item.get(k) == v for k, v in filters.items())]
        return items

    def count(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> int:
        return len(self.list(collection, filters))

    # ── 用户专用高效查询（不走 collections 表） ──

    def get_user(self, alpha_id: str) -> Optional[Dict[str, Any]]:
        with self._tx() as conn:
            row = conn.execute(
                "SELECT data FROM users WHERE alpha_id = ?",
                (alpha_id,),
            ).fetchone()
            return json.loads(row["data"]) if row else None

    def upsert_user(self, alpha_id: str, data: Dict):
        with self._tx() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO users (alpha_id, data) VALUES (?, ?)""",
                (alpha_id, json.dumps(data, ensure_ascii=False)),
            )

    def list_users(self) -> Dict[str, Any]:
        """返回 {alpha_id: data_dict} 格式"""
        with self._tx() as conn:
            rows = conn.execute("SELECT alpha_id, data FROM users").fetchall()
            return {row["alpha_id"]: json.loads(row["data"]) for row in rows}

    def add_friend(self, alpha_id: str, friend_id: str):
        with self._tx() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO social_friends (alpha_id, friend_id) VALUES (?, ?)",
                (alpha_id, friend_id),
            )

    def remove_friend(self, alpha_id: str, friend_id: str):
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM social_friends WHERE alpha_id = ? AND friend_id = ?",
                (alpha_id, friend_id),
            )

    def get_friends(self, alpha_id: str) -> List[str]:
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT friend_id FROM social_friends WHERE alpha_id = ?",
                (alpha_id,),
            ).fetchall()
            return [row["friend_id"] for row in rows]

    def are_friends(self, alpha_id_a: str, alpha_id_b: str) -> bool:
        """单向好友检查：仅检查 a 是否将 b 添加为好友"""
        with self._tx() as conn:
            row = conn.execute(
                "SELECT 1 FROM social_friends WHERE alpha_id = ? AND friend_id = ?",
                (alpha_id_a, alpha_id_b),
            ).fetchone()
            return row is not None
