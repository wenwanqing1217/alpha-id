#!/usr/bin/env python3
"""
Alpha-ID 数据迁移工具：JSON → PostgreSQL

用法：
    # 设置 DATABASE_URL 环境变量
    set DATABASE_URL=postgresql://user:pass@host:5432/aid

    # 执行迁移
    py scripts/migrate_to_postgres.py

    # 仅查看计划（不执行写入）
    py scripts/migrate_to_postgres.py --dry-run
"""

import argparse
import json
import os
import sys

# 将 src/ 加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.storage import JsonStorage
from core.storage_postgres import PostgresStorage


def migrate_users(json_storage: JsonStorage, pg_storage: PostgresStorage, dry_run: bool = False):
    """迁移用户数据"""
    users = json_storage.load("users") or {}
    counter = json_storage.load("counter") or 0
    founder = json_storage.load("founder_registered") or False

    print(f"[用户] 发现 {len(users)} 个用户")
    print(f"[用户] 计数器: {counter}, 创始人已注册: {founder}")

    if dry_run:
        return

    pg_storage.save("users", users)
    pg_storage.save("counter", counter)
    pg_storage.save("founder_registered", founder)
    print(f"[用户] ✓ 已迁移 {len(users)} 个用户")


def migrate_social(json_storage: JsonStorage, pg_storage: PostgresStorage, dry_run: bool = False):
    """迁移社交数据"""
    friends = json_storage.load("friends") or {}
    requests = json_storage.load("friend_requests") or {}
    messages = json_storage.load("messages") or {}

    friend_count = sum(len(v) for v in friends.values())
    print(f"[社交] 好友关系: {len(friends)} 人, {friend_count} 条关系")
    print(f"[社交] 好友请求: {len(requests)} 条")
    msg_count = sum(len(v) for v in messages.values())
    print(f"[社交] 消息: {msg_count} 条")

    if dry_run:
        return

    pg_storage.save("friends", friends)
    pg_storage.save("friend_requests", requests)
    pg_storage.save("messages", messages)
    print(f"[社交] ✓ 已迁移 {friend_count} 条好友关系, {len(requests)} 条请求, {msg_count} 条消息")


def main():
    parser = argparse.ArgumentParser(description="Alpha-ID JSON→PostgreSQL 迁移工具")
    parser.add_argument("--dry-run", action="store_true", help="仅查看计划，不执行写入")
    parser.add_argument("--assets-dir", default=None, help="JSON 资产目录（默认从 COZE_WORKSPACE_PATH/assets 推导）")
    args = parser.parse_args()

    # JSON 源路径
    assets_dir = args.assets_dir or os.path.join(
        os.getenv("COZE_WORKSPACE_PATH", os.path.join(os.path.dirname(__file__), "..")),
        "assets"
    )

    users_json_path = os.path.join(assets_dir, "alpha_id_users.json")
    social_json_path = os.path.join(assets_dir, "alpha_id_social.json")

    # 检查 JSON 数据是否存在
    if not os.path.exists(users_json_path) and not os.path.exists(social_json_path):
        print("⚠ 未找到 JSON 数据文件，没有数据需要迁移")
        return

    # 创建存储实例
    json_users = JsonStorage(users_json_path)
    json_social = JsonStorage(social_json_path)

    try:
        pg_storage = PostgresStorage()
    except ValueError as e:
        print(f"❌ PostgreSQL 连接失败: {e}")
        print("   请设置 DATABASE_URL 环境变量")
        sys.exit(1)

    print("=" * 50)
    print(f"  Alpha-ID 数据迁移: JSON → PostgreSQL")
    print(f"  {'只读预览' if args.dry_run else '执行迁移'}")
    print("=" * 50)
    print()

    if os.path.exists(users_json_path):
        migrate_users(json_users, pg_storage, dry_run=args.dry_run)
    else:
        print("[用户] 无用户数据文件")

    print()

    if os.path.exists(social_json_path):
        migrate_social(json_social, pg_storage, dry_run=args.dry_run)
    else:
        print("[社交] 无社交数据文件")

    print()
    if not args.dry_run:
        print("✅ 迁移完成！")
        print("   现有 JSON 文件未被删除，请确认数据正确后手动清除。")
        print("   切换存储后端：初始化时传入 PostgresStorage() 而非默认 JsonStorage。")
    else:
        print("🔍 预览完成。移除 --dry-run 执行实际迁移。")


if __name__ == "__main__":
    main()
