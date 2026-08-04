"""
Redis Client — 单例连接管理（用于 EventBus Redis Streams）

所有 Redis 操作通过此模块获取连接，避免重复创建连接池。
"""

import logging
import os
from typing import Optional

import redis

logger = logging.getLogger(__name__)

# 单例连接
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """获取 Redis 客户端（单例）"""
    global _redis_client
    if _redis_client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        logger.info("Redis client created: %s", url)
    return _redis_client


def close_redis_client():
    """关闭 Redis 连接"""
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None
        logger.info("Redis client closed")
