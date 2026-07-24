"""
依赖容器 — 替代模块级全局单例

提供：
- 单例管理（在 FastAPI lifespan 中初始化）
- lazy init + 线程安全
- 统一的存储后端切换点（SQLite / PostgreSQL）

存储后端选择：
- 默认：DATABASE_URL 环境变量决定（存在则用 Postgres，否则 SQLite）
- 测试：通过 storage setter 注入 mock
- 显式配置：os.environ["STORAGE_BACKEND"] = "sqlite" | "postgres"
"""

import logging
import os
import threading
from typing import Optional

from core.alpha_social import AlphaSocialManager
from core.memory_store import MemoryStore
from core.risk_engine import RiskAssessmentEngine
from core.storage import StorageBackend
from core.storage_sqlite import SqliteStorage
from core.user_identity import UserIdentityManager

logger = logging.getLogger(__name__)

# 显式后端选择（可选，覆盖自动检测）
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "").lower()


def _create_default_storage() -> StorageBackend:
    """根据环境自动选择存储后端"""
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_url.startswith("postgresql"):
        try:
            from core.storage_postgres import PostgresStorage
            logger.info("Using PostgreSQL storage backend")
            return PostgresStorage()
        except ImportError:
            logger.warning("psycopg not installed, falling back to SQLite")
    elif STORAGE_BACKEND == "postgres":
        from core.storage_postgres import PostgresStorage
        return PostgresStorage()
    elif STORAGE_BACKEND == "sqlite" or not database_url:
        pass  # fall through to SQLite
    logger.info("Using SQLite storage backend")
    return SqliteStorage()


class Container:
    """应用级依赖容器"""

    _instance: Optional["Container"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._storage: Optional[StorageBackend] = None
        self._identity: Optional[UserIdentityManager] = None
        self._social: Optional[AlphaSocialManager] = None
        self._risk: Optional[RiskAssessmentEngine] = None
        self._memory: Optional[MemoryStore] = None

    @classmethod
    def instance(cls) -> "Container":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 存储 ──

    @property
    def storage(self) -> StorageBackend:
        if self._storage is None:
            self._storage = _create_default_storage()
        return self._storage

    @storage.setter
    def storage(self, backend: StorageBackend):
        """允许测试注入 mock 或切换后端"""
        self._storage = backend
        # 重置已创建的 manager，使其下次用新存储重建
        self._identity = None
        self._social = None

    # ── Manager 实例（共享同一存储后端） ──

    @property
    def identity(self) -> UserIdentityManager:
        if self._identity is None:
            self._identity = UserIdentityManager(storage=self.storage)
        return self._identity

    @property
    def social(self) -> AlphaSocialManager:
        if self._social is None:
            self._social = AlphaSocialManager(storage=self.storage)
        return self._social

    @property
    def risk(self) -> RiskAssessmentEngine:
        if self._risk is None:
            self._risk = RiskAssessmentEngine()
        return self._risk

    @property
    def memory(self) -> MemoryStore:
        if self._memory is None:
            # 用第一个注册的用户的 alpha_id 初始化；没有用户时用占位符
            try:
                users = self.storage.load("users") or {}
                first_id = next(iter(users), "Alpha-001")
            except Exception:
                first_id = "Alpha-001"
            self._memory = MemoryStore(first_id, storage=self.storage)
        return self._memory

    # ── 生命周期 ──

    def reset(self):
        """测试用：清空所有单例"""
        self._storage = None
        self._identity = None
        self._social = None
        self._risk = None
        self._memory = None

    def close(self):
        """释放资源"""
        if hasattr(self._storage, "close"):
            self._storage.close()
