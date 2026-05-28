"""
MemoryStore 单元测试 —— 记忆存储 CRUD、查询、敏感度过滤
"""
import pytest
import json
import os
from core.memory_store import MemoryStore, AlphaMemory
from core.storage import JsonStorage


class TestAlphaMemoryModel:
    """AlphaMemory 数据模型测试"""

    def test_defaults(self):
        mem = AlphaMemory()
        assert mem.memory_id != ""
        assert mem.alpha_id == ""
        assert mem.content == ""
        assert mem.category == "general"
        assert mem.sensitivity == 0
        assert mem.source == "self"
        assert mem.tags == []

    def test_custom_values(self):
        mem = AlphaMemory(
            alpha_id="Alpha-Test",
            content="这是测试记忆",
            category="preference",
            sensitivity=30,
            source="social",
            tags=["test", "demo"]
        )
        assert mem.alpha_id == "Alpha-Test"
        assert mem.sensitivity == 30
        assert "test" in mem.tags


class TestMemoryStore:
    """MemoryStore 核心功能测试"""

    @pytest.fixture
    def store(self, tmp_path):
        """使用临时文件创建 MemoryStore"""
        db_path = str(tmp_path / "memory_test.json")
        storage = JsonStorage(db_path)
        return MemoryStore(alpha_id="Alpha-Mem-001", storage=storage)

    def test_init_creates_empty_store(self, store):
        """初始化后存储结构应为空"""
        memories = store._storage.load(store.alpha_id)
        assert memories == {}

    def test_save_memory(self, store):
        """保存一条记忆"""
        result = store.save(
            content="今天学了一个新知识点",
            category="knowledge",
            sensitivity=20,
            tags=["学习", "AI"]
        )
        assert result["success"] is True
        assert result["memory_id"] != ""

    def test_get_memory(self, store):
        """获取已保存的记忆"""
        saved = store.save(content="测试记忆")
        fetched = store.get(saved["memory_id"])
        assert fetched is not None
        assert fetched["content"] == "测试记忆"
        assert fetched["alpha_id"] == "Alpha-Mem-001"

    def test_get_nonexistent(self, store):
        """获取不存在的记忆"""
        fetched = store.get("nonexistent_id")
        assert fetched is None

    def test_query_by_keyword(self, store):
        """关键词搜索"""
        store.save(content="Java 是一种编程语言", tags=["java", "programming"])
        store.save(content="Python 也很流行", tags=["python", "programming"])
        store.save(content="今天天气很好", tags=["daily"])

        results = store.query(keyword="python", limit=10)
        assert len(results) == 1
        assert results[0]["content"] == "Python 也很流行"

    def test_query_by_tag(self, store):
        """通过标签搜索"""
        store.save(content="记忆A", tags=["tag1"])
        store.save(content="记忆B", tags=["tag2"])
        results = store.query(keyword="tag1", limit=10)
        assert len(results) == 1

    def test_query_case_insensitive(self, store):
        """关键词搜索大小写不敏感"""
        store.save(content="Hello World")
        results = store.query(keyword="hello", limit=10)
        assert len(results) == 1
        results = store.query(keyword="WORLD", limit=10)
        assert len(results) == 1

    def test_query_by_category(self, store):
        """分类过滤"""
        store.save(content="知识记忆", category="knowledge")
        store.save(content="社交记忆", category="social")
        results = store.query(category="knowledge", limit=10)
        assert len(results) == 1
        assert results[0]["content"] == "知识记忆"

    def test_query_by_sensitivity(self, store):
        """敏感度过滤"""
        store.save(content="公开信息", sensitivity=0)
        store.save(content="私密信息", sensitivity=80)
        results = store.query(max_sensitivity=50, limit=10)
        assert len(results) == 1
        assert results[0]["content"] == "公开信息"

    def test_query_combined_filters(self, store):
        """组合过滤"""
        store.save(content="公开知识", category="knowledge", sensitivity=0)
        store.save(content="私密知识", category="knowledge", sensitivity=80)
        store.save(content="社交信息", category="social", sensitivity=0)
        results = store.query(keyword="知识", category="knowledge", max_sensitivity=50, limit=10)
        assert len(results) == 1
        assert results[0]["content"] == "公开知识"

    def test_query_empty_keyword_returns_all(self, store):
        """空关键词返回所有匹配分类/敏感度的记忆"""
        store.save(content="记忆1", category="general")
        store.save(content="记忆2", category="general")
        results = store.query(limit=10)
        assert len(results) == 2

    def test_query_ordered_by_time(self, store):
        """按时间倒序"""
        import time
        store.save(content="第一条")
        time.sleep(0.01)
        store.save(content="第二条")
        results = store.query(limit=10)
        assert results[0]["content"] == "第二条"  # 最新的在前

    def test_query_limit(self, store):
        """limit 限制"""
        for i in range(5):
            store.save(content=f"记忆{i}")
        results = store.query(limit=3)
        assert len(results) == 3

    def test_delete_memory(self, store):
        """删除记忆"""
        saved = store.save(content="待删除")
        result = store.delete(saved["memory_id"])
        assert result["success"] is True
        assert store.get(saved["memory_id"]) is None

    def test_delete_nonexistent(self, store):
        """删除不存在的记忆"""
        result = store.delete("nonexistent")
        assert result["success"] is False

    def test_clear_all(self, store):
        """清空所有记忆"""
        store.save(content="记忆1")
        store.save(content="记忆2")
        result = store.clear()
        assert result["success"] is True
        assert store.count() == 0

    def test_count_all(self, store):
        """统计总数"""
        assert store.count() == 0
        store.save(content="记忆1")
        assert store.count() == 1
        store.save(content="记忆2")
        assert store.count() == 2

    def test_count_by_category(self, store):
        """按分类统计"""
        store.save(content="知识", category="knowledge")
        store.save(content="社交", category="social")
        store.save(content="更多知识", category="knowledge")
        assert store.count(category="knowledge") == 2
        assert store.count(category="social") == 1
        assert store.count(category="general") == 0

    def test_sensitivity_clamping(self, store):
        """敏感度自动限制在 0-100"""
        result = store.save(content="测试", sensitivity=-10)
        mem = store.get(result["memory_id"])
        assert mem["sensitivity"] == 0

        result = store.save(content="测试2", sensitivity=200)
        mem = store.get(result["memory_id"])
        assert mem["sensitivity"] == 100

    def test_list_by_sensitivity(self, store):
        """按敏感度列出"""
        store.save(content="公开", sensitivity=0)
        store.save(content="内部", sensitivity=40)
        store.save(content="机密", sensitivity=80)
        result = store.list_by_sensitivity(max_sensitivity=50)
        assert len(result) == 2
        assert all(m.get("sensitivity", 0) <= 50 for m in result)

    def test_save_without_tags(self, store):
        """不传 tags 默认空列表"""
        result = store.save(content="无标签记忆")
        mem = store.get(result["memory_id"])
        assert mem["tags"] == []

    def test_multiple_stores_independent(self, tmp_path):
        """不同 Alpha-ID 的记忆互不干扰"""
        path = str(tmp_path / "multi_mem.json")
        storage = JsonStorage(path)
        store1 = MemoryStore(alpha_id="Alpha-A", storage=storage)
        store2 = MemoryStore(alpha_id="Alpha-B", storage=storage)

        store1.save(content="A的记忆")
        store2.save(content="B的记忆")

        assert store1.count() == 1
        assert store2.count() == 1
        assert store1.query(keyword="B") == []  # A 搜不到 B 的记忆
