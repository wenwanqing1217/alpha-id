"""
异步存储和 LLM 客户端测试
"""

import asyncio
import os
import sys
import tempfile

import pytest

os.environ.setdefault("AUTH_MASTER_KEY", "test-master-key-for-pytest-0123456789abcdef")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.storage_async import AsyncSqliteStorage


class TestAsyncSqliteStorage:
    """异步 SQLite 存储测试"""

    @pytest.fixture
    def storage(self, tmp_path):
        """临时存储"""
        db_path = str(tmp_path / "test.db")
        return AsyncSqliteStorage(db_path)

    @pytest.mark.asyncio
    async def test_save_and_load(self, storage):
        """保存后能加载"""
        await storage.save("test_key", {"name": "Alice", "age": 30})
        loaded = await storage.load("test_key")
        assert loaded is not None
        assert loaded["name"] == "Alice"
        assert loaded["age"] == 30
        await storage.close()

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, storage):
        """加载不存在的 key 返回 None"""
        result = await storage.load("nonexistent")
        assert result is None
        await storage.close()

    @pytest.mark.asyncio
    async def test_overwrite(self, storage):
        """保存覆盖已有数据"""
        await storage.save("key", {"v": 1})
        await storage.save("key", {"v": 2})
        loaded = await storage.load("key")
        assert loaded["v"] == 2
        await storage.close()

    @pytest.mark.asyncio
    async def test_put_and_get(self, storage):
        """单条记录的 put/get"""
        await storage.put("users", "user_1", {"name": "Bob"})
        record = await storage.get("users", "user_1")
        assert record is not None
        assert record["name"] == "Bob"
        await storage.close()

    @pytest.mark.asyncio
    async def test_delete(self, storage):
        """删除记录"""
        await storage.put("users", "user_1", {"name": "Bob"})
        await storage.delete("users", "user_1")
        record = await storage.get("users", "user_1")
        assert record is None
        await storage.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, tmp_path):
        """上下文管理器正确开关连接"""
        db_path = str(tmp_path / "ctx.db")
        async with AsyncSqliteStorage(db_path) as storage:
            await storage.save("k", {"v": 1})
            loaded = await storage.load("k")
            assert loaded["v"] == 1

    @pytest.mark.asyncio
    async def test_sequential_writes(self, storage):
        """串行写入多条数据，验证一致性（单连接串行执行）"""
        for i in range(10):
            await storage.save(f"key_{i}", {"index": i})

        for i in range(10):
            loaded = await storage.load(f"key_{i}")
            assert loaded["index"] == i
        await storage.close()

    @pytest.mark.asyncio
    async def test_unicode_content(self, storage):
        """中文/Unicode 内容正确存储"""
        data = {"name": "张三", "desc": "数字身份系统 🎉"}
        await storage.save("unicode_key", data)
        loaded = await storage.load("unicode_key")
        assert loaded["name"] == "张三"
        assert loaded["desc"] == "数字身份系统 🎉"
        await storage.close()


class TestAsyncLLMClient:
    """异步 LLM 客户端测试（不实际调用 API）"""

    def test_client_init_with_defaults(self):
        """默认配置初始化"""
        from core.llm_async import AsyncLLMClient
        client = AsyncLLMClient(api_key="test-key", base_url="https://api.test.com/v1", model="test-model")
        assert client.api_key == "test-key"
        assert client.base_url == "https://api.test.com/v1"
        assert client.model == "test-model"

    def test_client_init_from_settings(self):
        """从 settings 初始化"""
        from core.llm_async import AsyncLLMClient
        client = AsyncLLMClient()
        # api_key 来自 settings（测试环境可能为空）
        assert client.base_url.endswith("/v1") or "api" in client.base_url

    @pytest.mark.asyncio
    async def test_client_close(self):
        """关闭客户端不报错"""
        from core.llm_async import AsyncLLMClient
        client = AsyncLLMClient(api_key="test", base_url="https://test.com", model="test")
        # 未使用直接关闭
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """上下文管理器"""
        from core.llm_async import AsyncLLMClient
        async with AsyncLLMClient(api_key="test", base_url="https://test.com", model="test") as client:
            assert client is not None
