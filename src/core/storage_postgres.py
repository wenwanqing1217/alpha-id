"""
PostgreSQL 存储后端

实现 StorageBackend 接口，使用 psycopg（同步）+ connection pooling。
通过 DATABASE_URL 环境变量连接，支持连接池复用和事务。
"""

import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import psycopg
import psycopg.rows
from psycopg_pool import ConnectionPool

from core.storage import StorageBackend

logger = logging.getLogger(__name__)


def _get_database_url() -> str:
    """从环境变量获取 PostgreSQL 连接串"""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL environment variable is required for PostgresStorage. "
            "Example: postgresql://user:pass@host:5432/dbname"
        )
    return url


class PostgresStorage(StorageBackend):
    """PostgreSQL 存储后端（连接池，线程安全）"""

    def __init__(self, database_url: Optional[str] = None, min_size: int = 2, max_size: int = 10):
        self.database_url = database_url or _get_database_url()
        self._pool = ConnectionPool(
            conninfo=self.database_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": psycopg.rows.dict_row},
        )
        self._init_schema()
        logger.info("PostgresStorage initialized (pool %s-%s)", min_size, max_size)

    # ── 连接管理 ──

    @contextmanager
    def _conn(self):
        """从连接池获取连接，自动归还"""
        with self._pool.connection() as conn:
            yield conn

    @contextmanager
    def _tx(self):
        """事务上下文（自动提交/回滚）"""
        with self._pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def close(self):
        """关闭连接池"""
        self._pool.close()
        logger.info("PostgresStorage pool closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # ── 建表 ──

    def _init_schema(self):
        """初始化数据库 schema（幂等）"""
        schema = """
        CREATE TABLE IF NOT EXISTS collections (
            collection_name TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL DEFAULT '_default',
            data JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX IF NOT EXISTS idx_collections_name ON collections(collection_name);

        CREATE TABLE IF NOT EXISTS users (
            alpha_id TEXT PRIMARY KEY,
            data JSONB NOT NULL DEFAULT '{}'::jsonb
        );

        CREATE TABLE IF NOT EXISTS social_friends (
            alpha_id TEXT NOT NULL,
            friend_id TEXT NOT NULL,
            PRIMARY KEY (alpha_id, friend_id)
        );
        CREATE INDEX IF NOT EXISTS idx_friends_alpha ON social_friends(alpha_id);

        CREATE TABLE IF NOT EXISTS social_requests (
            request_id TEXT PRIMARY KEY,
            data JSONB NOT NULL DEFAULT '{}'::jsonb
        );

        CREATE TABLE IF NOT EXISTS social_messages (
            message_id TEXT PRIMARY KEY,
            data JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        """
        with self._tx() as conn:
            conn.execute(schema)

    # ── JSON 序列化辅助 ──

    @staticmethod
    def _serialize(record: Dict[str, Any]) -> str:
        return json.dumps(record, ensure_ascii=False)

    @staticmethod
    def _deserialize(raw: str) -> Dict[str, Any]:
        return json.loads(raw)

    # ── StorageBackend 接口实现 ──

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载整个集合"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM collections WHERE collection_name = %s",
                (key,),
            ).fetchone()
            if row is None:
                return None
            data = row["data"]
            # psycopb returns JSONB as dict directly
            return data if isinstance(data, dict) else self._deserialize(data)

    def save(self, key: str, data: Dict[str, Any]):
        """保存整个集合"""
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO collections (collection_name, doc_id, data)
                   VALUES (%s, '_default', %s::jsonb)
                   ON CONFLICT (collection_name)
                   DO UPDATE SET doc_id = EXCLUDED.doc_id, data = EXCLUDED.data""",
                (key, self._serialize(data)),
            )

    def get(self, collection: str, record_id: str) -> Optional[Dict[str, Any]]:
        """获取单条记录"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM collections WHERE collection_name = %s",
                (f"{collection}_item_{record_id}",),
            ).fetchone()
            if row is None:
                return None
            data = row["data"]
            return data if isinstance(data, dict) else self._deserialize(data)

    def put(self, collection: str, record_id: str, record: Dict[str, Any]):
        """写入单条记录"""
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO collections (collection_name, doc_id, data)
                   VALUES (%s, '_default', %s::jsonb)
                   ON CONFLICT (collection_name)
                   DO UPDATE SET doc_id = EXCLUDED.doc_id, data = EXCLUDED.data""",
                (f"{collection}_item_{record_id}", self._serialize(record)),
            )

    def delete(self, collection: str, record_id: str):
        """删除单条记录"""
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM collections WHERE collection_name = %s",
                (f"{collection}_item_{record_id}",),
            )

    def list(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """列出集合中的记录"""
        data = self.load(collection)
        if data is None:
            return []
        items = list(data.values())
        if filters:
            items = [item for item in items if all(item.get(k) == v for k, v in filters.items())]
        return items

    def count(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> int:
        return len(self.list(collection, filters))

    # ── 用户专用高效查询 ──

    def get_user(self, alpha_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM users WHERE alpha_id = %s",
                (alpha_id,),
            ).fetchone()
            if row is None:
                return None
            data = row["data"]
            return data if isinstance(data, dict) else self._deserialize(data)

    def upsert_user(self, alpha_id: str, data: Dict):
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO users (alpha_id, data) VALUES (%s, %s::jsonb)
                   ON CONFLICT (alpha_id) DO UPDATE SET data = EXCLUDED.data""",
                (alpha_id, self._serialize(data)),
            )

    def list_users(self) -> Dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute("SELECT alpha_id, data FROM users").fetchall()
            return {
                row["alpha_id"]: (row["data"] if isinstance(row["data"], dict) else self._deserialize(row["data"]))
                for row in rows
            }

    # ── 社交关系 ──

    def add_friend(self, alpha_id: str, friend_id: str):
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO social_friends (alpha_id, friend_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (alpha_id, friend_id),
            )

    def remove_friend(self, alpha_id: str, friend_id: str):
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM social_friends WHERE alpha_id = %s AND friend_id = %s",
                (alpha_id, friend_id),
            )

    def get_friends(self, alpha_id: str) -> List[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT friend_id FROM social_friends WHERE alpha_id = %s",
                (alpha_id,),
            ).fetchall()
            return [row["friend_id"] for row in rows]

    def are_friends(self, alpha_id_a: str, alpha_id_b: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM social_friends WHERE alpha_id = %s AND friend_id = %s",
                (alpha_id_a, alpha_id_b),
            ).fetchone()
            return row is not None
