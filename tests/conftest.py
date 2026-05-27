"""pytest 共享配置"""
import sys
import os

# 将 src 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest


@pytest.fixture
def temp_json_db(tmp_path):
    """创建临时 JSON 数据库文件，用于测试 UserIdentityManager"""
    import json
    db_path = tmp_path / "alpha_id_users.json"
    db_path.write_text(
        json.dumps({"users": {}, "counter": 0, "founder_registered": False}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return str(db_path)


@pytest.fixture
def temp_social_db(tmp_path):
    """创建临时社交 JSON 数据库文件，用于测试 AlphaSocialManager"""
    import json
    db_path = tmp_path / "alpha_id_social.json"
    db_path.write_text(
        json.dumps({"friends": {}, "friend_requests": {}, "messages": {}}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return str(db_path)
