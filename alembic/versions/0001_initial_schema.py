"""initial schema baseline

Revision ID: 0001
Revises:
Create Date: 2026-07-27 00:00:00

将现有 SqliteStorage 的 schema 记录为基线迁移。
后续 schema 变更通过 `alembic revision --autogenerate` 生成。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建初始 schema（与 SqliteStorage._init_schema 一致）"""
    # collections 表 — 通用键值存储
    op.create_table(
        "collections",
        sa.Column("collection_name", sa.Text, primary_key=True),
        sa.Column("doc_id", sa.Text, nullable=False, server_default="_default"),
        sa.Column("data", sa.Text, nullable=False, server_default="{}"),
    )
    op.create_index("idx_collections_name", "collections", ["collection_name"])

    # users 表
    op.create_table(
        "users",
        sa.Column("alpha_id", sa.Text, primary_key=True),
        sa.Column("data", sa.Text, nullable=False),
    )

    # social_friends 表
    op.create_table(
        "social_friends",
        sa.Column("alpha_id", sa.Text, nullable=False),
        sa.Column("friend_id", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("alpha_id", "friend_id"),
    )
    op.create_index("idx_friends_alpha", "social_friends", ["alpha_id"])

    # social_requests 表
    op.create_table(
        "social_requests",
        sa.Column("request_id", sa.Text, primary_key=True),
        sa.Column("data", sa.Text, nullable=False),
    )
    op.create_index("idx_requests_to", "social_requests", ["json_extract(data, '$.to_alpha_id')"])

    # social_messages 表
    op.create_table(
        "social_messages",
        sa.Column("message_id", sa.Text, primary_key=True),
        sa.Column("data", sa.Text, nullable=False),
    )
    op.create_index("idx_messages_to", "social_messages", ["json_extract(data, '$.to_alpha_id')"])

    # alembic_version 表由 Alembic 自动管理


def downgrade() -> None:
    """回滚到空数据库"""
    op.drop_table("social_messages")
    op.drop_table("social_requests")
    op.drop_table("social_friends")
    op.drop_table("users")
    op.drop_index("idx_collections_name", table_name="collections")
    op.drop_table("collections")
