"""
Storage Factory —— 存储后端工厂

根据环境变量自动选择存储后端：
  - DATABASE_URL 已设置 → PostgreSQL（生产）
  - STORAGE_BACKEND=sqlite → SQLite（默认，零依赖，WAL 模式）
  - STORAGE_BACKEND=json → JSON 文件（兼容旧版）

用法：
  from core.storage_factory import get_storage
  storage = get_storage()  # 自动选择
"""
import logging

from core.settings import settings
from core.storage import JsonStorage, StorageBackend
from core.storage_sqlite import SqliteStorage

logger = logging.getLogger(__name__)


def get_storage(db_path: str = None) -> StorageBackend:
    """
    获取存储后端（自动选择）

    优先级：
    1. DATABASE_URL 环境变量 → PostgreSQL
    2. STORAGE_BACKEND 显式配置
    3. 默认 → SQLite（零外部依赖，WAL 模式，线程安全）

    Args:
        db_path: JSON 文件路径（仅 JSON 模式使用）

    Returns:
        StorageBackend 实例
    """
    database_url = settings.database_url

    if database_url:
        try:
            from core.storage_postgres import PostgresStorage
            storage = PostgresStorage(database_url=database_url)
            logger.info("存储后端: PostgreSQL (连接池)")
            return storage
        except Exception as e:
            logger.warning("PostgreSQL 连接失败，降级为 SQLite: %s", e)
            return SqliteStorage()

    # 显式后端选择（可选）
    backend = settings.storage_backend
    if backend == "json":
        if db_path is None:
            db_path = str(settings.ghost_workspace / "assets" / "ghost_data.json")
        storage = JsonStorage(db_path)
        logger.info("存储后端: JSON (%s)", db_path)
        return storage

    # 默认：SQLite（WAL 模式，线程安全，零外部依赖）
    logger.info("存储后端: SQLite (WAL)")
    return SqliteStorage()


def get_storage_for_tenant(tenant_id: str) -> StorageBackend:
    """
    获取租户专用存储后端

    多租户模式下，每个租户可以使用独立的数据库或 schema。
    当前实现：共享存储，数据层通过 tenant_id 隔离。
    """
    return get_storage()
