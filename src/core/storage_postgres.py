"""
PostgreSQL 存储后端（SQLAlchemy 实现）

需要环境变量 DATABASE_URL 或 COZE_SUPABASE_URL 指向 PostgreSQL 数据库。
"""

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from core.storage import StorageBackend

# 模型映射：集合名称 → SQLAlchemy 模型
_COLLECTION_MODEL_MAP: Dict[str, str] = {}

# 注册的回调：集合名 → 处理函数
_COLLECTION_HANDLERS: Dict[str, Dict[str, Any]] = {}


def _get_database_url() -> str:
    """获取数据库连接 URL"""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    url = os.getenv("COZE_SUPABASE_URL")
    if url:
        # Supabase 的 URL 需要连接池配置
        return url.replace("https://", "postgresql://")
    raise ValueError(
        "需要设置 DATABASE_URL 或 COZE_SUPABASE_URL 环境变量"
    )


class PostgresStorage(StorageBackend):
    """PostgreSQL 存储后端"""

    def __init__(self, database_url: Optional[str] = None):
        self._database_url = database_url or _get_database_url()
        self._engine = create_engine(
            self._database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        self._SessionLocal = sessionmaker(bind=self._engine)

    @contextmanager
    def _session(self) -> Session:
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- 通用接口（简化版，基于原生 SQL） ----

    def _table_exists(self, table_name: str) -> bool:
        with self._session() as session:
            result = session.execute(
                text(
                    "SELECT EXISTS ("
                    "  SELECT FROM information_schema.tables "
                    "  WHERE table_name = :name"
                    ")"
                ),
                {"name": table_name},
            )
            return result.scalar()

    def _ensure_table(self, table_name: str, schema_sql: str):
        if not self._table_exists(table_name):
            with self._session() as session:
                session.execute(text(schema_sql))
                session.commit()

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        # 整体加载仅用于兼容 JSON 模式，Postgres 模式按 key 区分表
        raise NotImplementedError("PostgresStorage.load 未实现——请使用集合级方法 (list/get/put)")

    def save(self, key: str, data: Dict[str, Any]):
        raise NotImplementedError("PostgresStorage.save 未实现——请使用集合级方法 (list/get/put)")

    def get(self, collection: str, record_id: str) -> Optional[Dict[str, Any]]:
        handler = _COLLECTION_HANDLERS.get(collection, {}).get("get")
        if handler:
            return handler(record_id)
        # 通用实现：假设表有 id 主键
        table_name = f"aid_{collection}"
        if not self._table_exists(table_name):
            return None
        with self._session() as session:
            result = session.execute(
                text(f"SELECT * FROM {table_name} WHERE id = :rid"),
                {"rid": record_id},
            )
            row = result.mappings().first()
            return dict(row) if row else None

    def put(self, collection: str, record_id: str, record: Dict[str, Any]):
        handler = _COLLECTION_HANDLERS.get(collection, {}).get("put")
        if handler:
            handler(record_id, record)
            return
        table_name = f"aid_{collection}"
        existing = self.get(collection, record_id)
        if existing:
            sets = ", ".join(
                f"\"{k}\" = :v{k}" for k in record
            )
            params = {f"v{k}": v for k, v in record.items()}
            params["rid"] = record_id
            with self._session() as session:
                session.execute(
                    text(f"UPDATE {table_name} SET {sets} WHERE id = :rid"),
                    params,
                )
        else:
            cols = ", ".join(f"\"{k}\"" for k in record)
            vals = ", ".join(f":v{k}" for k in record)
            params = {f"v{k}": v for k, v in record.items()}
            with self._session() as session:
                session.execute(
                    text(f"INSERT INTO {table_name} ({cols}) VALUES ({vals})"),
                    params,
                )

    def delete(self, collection: str, record_id: str):
        handler = _COLLECTION_HANDLERS.get(collection, {}).get("delete")
        if handler:
            handler(record_id)
            return
        table_name = f"aid_{collection}"
        with self._session() as session:
            session.execute(
                text(f"DELETE FROM {table_name} WHERE id = :rid"),
                {"rid": record_id},
            )

    def list(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        handler = _COLLECTION_HANDLERS.get(collection, {}).get("list")
        if handler:
            return handler(filters)
        table_name = f"aid_{collection}"
        if not self._table_exists(table_name):
            return []
        with self._session() as session:
            if filters:
                conditions = " AND ".join(
                    f"\"{k}\" = :v{k}" for k in filters
                )
                params = {f"v{k}": v for k, v in filters.items()}
                result = session.execute(
                    text(f"SELECT * FROM {table_name} WHERE {conditions}"),
                    params,
                )
            else:
                result = session.execute(text(f"SELECT * FROM {table_name}"))
            return [dict(row) for row in result.mappings().all()]

    def count(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> int:
        return len(self.list(collection, filters))
