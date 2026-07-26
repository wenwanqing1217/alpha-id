"""Alembic 迁移环境配置"""

from logging.config import fileConfig
import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 将 src 加入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.settings import settings

config = context.config

# 从 settings 动态设置数据库 URL
if settings.database_url:
    config.set_main_option("sqlalchemy.url", settings.database_url)
else:
    db_path = os.path.join(str(settings.ghost_workspace), "assets", "alpha_id.db")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入所有模型，确保 Alembic 能自动检测变更
try:
    from core.storage_sqlite import SqliteStorage  # noqa: F401
    # 这里导入所有需要迁移的模型
    target_metadata = None  # 使用 autogenerate 时需要设置
except ImportError:
    target_metadata = None


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直接执行迁移"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
