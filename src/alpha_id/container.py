"""
依赖容器 — 替代模块级全局单例

提供：
- 单例管理（在 FastAPI lifespan 中初始化）
- lazy init + 线程安全
- 统一的存储后端切换点（SQLite / PostgreSQL）
- FastAPI 依赖注入支持（get_container）

存储后端选择：
- 默认：DATABASE_URL 环境变量决定（存在则用 Postgres，否则 SQLite）
- 测试：通过 storage setter 注入 mock
- 显式配置：os.environ["STORAGE_BACKEND"] = "sqlite" | "postgres"

依赖注入迁移（Phase 2）：
- 旧代码：Container.instance().xxx
- 新代码：在 FastAPI 路由中使用 Depends(get_container)
- 本文件保留 instance() 单例以兼容非 FastAPI 上下文（CLI、web.py）
"""

import logging
import threading
from typing import Optional

from core.settings import settings

from core.alpha_social import AlphaSocialManager
from core.memory_store import MemoryStore
from core.risk_engine import RiskAssessmentEngine
from core.storage import StorageBackend
from core.storage_sqlite import SqliteStorage
from core.user_identity import UserIdentityManager

logger = logging.getLogger(__name__)

# 显式后端选择（可选，覆盖自动检测）
STORAGE_BACKEND = settings.storage_backend


def _create_default_storage() -> StorageBackend:
    """根据环境自动选择存储后端"""
    database_url = settings.database_url
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
        """获取全局单例（线程安全）

        兼容旧代码。新代码应在 FastAPI 上下文中使用 Depends(get_container)。
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, container: "Container") -> None:
        """显式设置单例（用于测试注入或自定义初始化）"""
        with cls._lock:
            cls._instance = container

    @classmethod
    def reset_instance(cls) -> None:
        """清除单例（测试用）"""
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.close()
                except Exception:
                    pass
                cls._instance = None

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
            # 注入用户存在性检查回调（H4: 社交功能验证目标用户存在）
            identity = self.identity
            self._social = AlphaSocialManager(
                storage=self.storage,
                user_exists_fn=identity.user_exists,
            )
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


# ── FastAPI 依赖注入 ──

try:
    from fastapi import Depends, Request

    def get_container(request: Request) -> Container:
        """FastAPI 依赖：从 app.state 获取 Container

        使用方式：
            @router.get("/xxx")
            def handler(container: Container = Depends(get_container)):
                ...

        优势：
        - 测试时可注入 mock container
        - 支持请求级别的容器隔离（多租户）
        - 消除对全局单例的直接依赖

        兼容回退：如果 app.state.container 未设置（例如 TestClient 未运行 lifespan），
        回退到全局单例 Container.instance()，保证非生产环境可用。
        """
        try:
            return request.app.state.container
        except AttributeError:
            return Container.instance()

    def _get_container_from_app(app) -> Optional[Container]:
        """从 FastAPI app 实例获取容器（非请求上下文使用）"""
        return getattr(app.state, "container", None)

except ImportError:
    # FastAPI 不可用时提供占位
    def get_container(request=None) -> Container:  # type: ignore[misc]
        """FastAPI 不可用，回退到单例"""
        return Container.instance()
