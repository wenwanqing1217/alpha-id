"""
异步 SQLite 存储后端 — 基于 aiosqlite

用于异步上下文（FastAPI async 路由）中执行 DB 操作，
避免阻塞事件循环。与 SqliteStorage 保持 API 兼容。
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import aiosqlite

from core.settings import settings


class AsyncSqliteStorage:
    """异步 SQLite 存储后端（线程安全，WAL 模式）"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(str(settings.ghost_workspace), "assets", "alpha_id.db")
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._init_lock = asyncio.Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    async def _get_conn(self) -> aiosqlite.Connection:
        """获取连接（惰性创建，带锁防并发初始化）"""
        if self._conn is None:
            async with self._init_lock:
                # double-check，防止锁内重复初始化
                if self._conn is None:
                    self._conn = await aiosqlite.connect(self.db_path)
                    self._conn.row_factory = aiosqlite.Row
                    await self._conn.execute("PRAGMA journal_mode=WAL")
                    await self._conn.execute("PRAGMA synchronous=NORMAL")
                    await self._conn.execute("PRAGMA foreign_keys=ON")
                    await self._init_schema()
        return self._conn

    async def _init_schema(self):
        """初始化 schema（与同步版一致）"""
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

        CREATE TABLE IF NOT EXISTS social_requests (
            request_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS social_messages (
            message_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        """
        if self._conn:
            await self._conn.executescript(schema)
            await self._conn.commit()

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        """异步加载集合"""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT data FROM collections WHERE collection_name = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return json.loads(row["data"])

    async def save(self, key: str, data: Dict[str, Any]) -> None:
        """异步保存集合"""
        conn = await self._get_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO collections (collection_name, doc_id, data)
               VALUES (?, '_default', ?)""",
            (key, json.dumps(data, ensure_ascii=False)),
        )
        await conn.commit()

    async def get(self, collection: str, record_id: str) -> Optional[Dict[str, Any]]:
        """异步获取单条记录"""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT data FROM collections WHERE collection_name = ?",
            (f"{collection}_item_{record_id}",),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return json.loads(row["data"])

    async def put(self, collection: str, record_id: str, record: Dict[str, Any]) -> None:
        """异步写入单条记录"""
        conn = await self._get_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO collections (collection_name, doc_id, data)
               VALUES (?, '_default', ?)""",
            (f"{collection}_item_{record_id}", json.dumps(record, ensure_ascii=False)),
        )
        await conn.commit()

    async def delete(self, collection: str, record_id: str) -> None:
        """异步删除单条记录"""
        conn = await self._get_conn()
        await conn.execute(
            "DELETE FROM collections WHERE collection_name = ?",
            (f"{collection}_item_{record_id}",),
        )
        await conn.commit()

    async def close(self) -> None:
        """关闭连接"""
        if self._conn:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None

    async def __aenter__(self):
        await self._get_conn()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
