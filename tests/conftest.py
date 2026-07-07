"""pytest 共享配置"""

import sys
import os

# 将 src 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── 模拟 langchain.tools ──────────────────────────────────────────────
# 某些工具模块引用了 @tool 装饰器 / ToolRuntime，在 CI/测试环境不安装 langchain
# 因此提供浅层桩模块，确保 import 通过即可。
if "langchain" not in sys.modules:

    class _ToolRuntime:
        pass

    class _Tool:
        def __call__(self, func):
            func._is_tool = True
            return func

    import types

    _langchain_mod = types.ModuleType("langchain")
    _langchain_tools_mod = types.ModuleType("langchain.tools")
    _langchain_tools_mod.tool = _Tool()
    _langchain_tools_mod.ToolRuntime = _ToolRuntime
    _langchain_mod.tools = _langchain_tools_mod

    sys.modules["langchain"] = _langchain_mod
    sys.modules["langchain.tools"] = _langchain_tools_mod

import pytest


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    """自动设置测试环境变量，将数据目录指向临时目录"""
    old_alpha_id_dir = os.environ.get("ALPHA_ID_DIR")
    old_aid_dir = os.environ.get("AID_DIR")

    os.environ["ALPHA_ID_DIR"] = str(tmp_path / "alpha-id")
    os.environ["AID_DIR"] = str(tmp_path / "aid")

    yield

    if old_alpha_id_dir is not None:
        os.environ["ALPHA_ID_DIR"] = old_alpha_id_dir
    else:
        os.environ.pop("ALPHA_ID_DIR", None)

    if old_aid_dir is not None:
        os.environ["AID_DIR"] = old_aid_dir
    else:
        os.environ.pop("AID_DIR", None)


@pytest.fixture
def temp_json_db(tmp_path):
    """创建临时 JSON 数据库文件，用于测试 UserIdentityManager"""
    import json

    db_path = tmp_path / "alpha_id_users.json"
    db_path.write_text(
        json.dumps({"users": {}, "counter": 0, "founder_registered": False}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(db_path)


@pytest.fixture
def temp_social_db(tmp_path):
    """创建临时社交 JSON 数据库文件，用于测试 AlphaSocialManager"""
    import json

    db_path = tmp_path / "alpha_id_social.json"
    db_path.write_text(
        json.dumps({"friends": {}, "friend_requests": {}, "messages": {}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(db_path)
