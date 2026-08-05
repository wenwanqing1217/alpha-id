"""
统一重试策略 — 基于 tenacity

替代散落各处的手写 for attempt/range 重试循环。
支持：指数退避、最大重试次数、超时、自定义异常过滤。
"""

import logging
import sqlite3
from typing import Callable, Optional, Tuple, Type

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


def create_retry_decorator(
    max_attempts: int = 3,
    wait_multiplier: float = 1.0,
    wait_max: float = 60.0,
    retry_exceptions: Optional[Tuple[Type[BaseException], ...]] = None,
) -> Callable:
    """创建统一重试装饰器

    Args:
        max_attempts: 最大重试次数
        wait_multiplier: 指数退避系数（秒）
        wait_max: 最大等待时间（秒）
        retry_exceptions: 需要重试的异常类型元组，默认 (OSError, ConnectionError, TimeoutError)
    """
    if retry_exceptions is None:
        retry_exceptions = (OSError, ConnectionError, TimeoutError)

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=wait_multiplier, max=wait_max),
        retry=retry_if_exception_type(retry_exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def llm_retry(max_attempts: int = 3) -> Callable:
    """LLM 调用专用重试（更激进的重试策略）"""
    return create_retry_decorator(
        max_attempts=max_attempts,
        wait_multiplier=2.0,
        wait_max=30.0,
        retry_exceptions=(OSError, ConnectionError, TimeoutError, ValueError),
    )


def http_retry(max_attempts: int = 3) -> Callable:
    """HTTP 请求专用重试"""
    return create_retry_decorator(
        max_attempts=max_attempts,
        wait_multiplier=1.0,
        wait_max=10.0,
    )


def db_retry(max_attempts: int = 5) -> Callable:
    """数据库操作专用重试（更多次数，更短间隔）"""
    return create_retry_decorator(
        max_attempts=max_attempts,
        wait_multiplier=0.5,
        wait_max=5.0,
        retry_exceptions=(OSError, sqlite3.OperationalError, TimeoutError),
    )
