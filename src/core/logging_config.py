"""
结构化日志配置 — structlog + 标准库 logging 桥接

生产环境输出 JSON（便于 ELK / Loki 聚合），开发环境输出彩色文本。
自动脱敏敏感数据（通过 SensitiveDataFilter）。

用法：
    from core.logging_config import configure_logging
    configure_logging()  # 在应用启动时调用一次

    import structlog
    logger = structlog.get_logger()
    logger.info("user_login", alpha_id="Alpha-001", ip="1.2.3.4")
"""

import logging
import sys
from typing import Optional

from core.settings import settings


def _has_structlog() -> bool:
    """检查 structlog 是否可用"""
    try:
        import structlog  # noqa: F401

        return True
    except ImportError:
        return False


def configure_logging(level: Optional[str] = None) -> None:
    """
    配置结构化日志

    优先级：
    1. 显式传入的 level 参数
    2. LOG_LEVEL 环境变量
    3. 默认 INFO

    生产环境（settings.is_production）输出 JSON；
    开发环境输出彩色文本。
    """
    log_level = level or settings.log_level

    if _has_structlog():
        _configure_structlog(log_level)
    else:
        _configure_standard_logging(log_level)

    # 安装敏感数据过滤器（无论哪种日志后端）
    from core.logging_filter import install_sensitive_data_filter

    install_sensitive_data_filter()


def _configure_structlog(log_level: str) -> None:
    """配置 structlog（JSON 或彩色文本）"""
    import structlog

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        # 生产环境：JSON 格式
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # 开发环境：彩色文本
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 桥接标准库 logging → structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=_parse_level(log_level),
    )


def _configure_standard_logging(log_level: str) -> None:
    """标准库 logging 回退配置"""
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        level=_parse_level(log_level),
    )


def _parse_level(level: str) -> int:
    """解析日志级别字符串"""
    return getattr(logging, level.upper(), logging.INFO)
