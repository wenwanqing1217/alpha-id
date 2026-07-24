"""
Storage Factory —— 存储后端工厂

根据环境变量自动选择存储后端：
  - DATABASE_URL 已设置 → PostgreSQL（生产）
  - 未设置 → JSON 文件（开发）

用法：
  from core.storage_factory import get_storage
  storage = get_storage()  # 自动选择
"""
import logging
import os
from typing import Optional

from core.storage import StorageBackend, JsonStorage

logger = logging.getLogger(__name__)


def get_storage(db_path: str = None) -> StorageBackend:
    """
    获取存储后端（自动选择）

    优先级：
    1. DATABASE_URL 环境变量 → PostgreSQL
    2. 否则 → JSON 文件

    Args:
        db_path: JSON 文件路径（仅 JSON 模式使用）

    Returns:
        StorageBackend 实例
    """
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        try:
            from core.storage_postgres import PostgresStorage
            storage = PostgresStorage(database_url=database_url)
            logger.info("存储后端: PostgreSQL (连接池)")
            return storage
        except Exception as e:
            logger.warning(f"PostgreSQL 连接失败，降级为 JSON: {e}")

    # 默认：JSON 文件
    if db_path is None:
        db_path = os.path.join(
            os.getenv("GHOST_WORKSPACE_PATH", os.getcwd()),
            "assets",
            "ghost_data.json",
        )
    storage = JsonStorage(db_path)
    logger.info(f"存储后端: JSON ({db_path})")
    return storage


def get_storage_for_tenant(tenant_id: str) -> StorageBackend:
    """
    获取租户专用存储后端
    
    多租户模式下，每个租户可以使用独立的数据库或 schema。
    当前实现：共享存储，数据层通过 tenant_id 隔离。
    """
    return get_storage()
