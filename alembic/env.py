"""Alembic migration environment config

NOTE: This project uses raw sqlite3 (not SQLAlchemy ORM models) for data access.
Therefore `alembic revision --autogenerate` will NOT detect schema changes.
All future migrations must be hand-written in alembic/versions/.
"""

from logging.config import fileConfig
import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, MetaData, pool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.settings import settings

config = context.config

if settings.database_url:
    config.set_main_option("sqlalchemy.url", settings.database_url)
else:
    db_path = os.path.join(str(settings.alpha_id_path), "alpha_id.db")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = MetaData()


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
