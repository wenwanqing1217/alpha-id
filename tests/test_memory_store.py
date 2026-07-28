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
            tags=["test", "demo"],
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
        result = store.save(content="今天学了一个新知识点", category="knowledge", sensitivity=20, tags=["学习", "AI"])
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

    # ── update 测试 ──

    def test_update_content_only(self, store):
        """只更新内容，其他字段不变"""
        result = store.save(content="旧内容", category="tech", tags=["a"])
        mid = result["memory_id"]

        r2 = store.update(memory_id=mid, content="新内容")
        assert r2["success"] is True

        mem = store.get(mid)
        assert mem["content"] == "新内容"
        assert mem["category"] == "tech"  # 不变
        assert mem["tags"] == ["a"]  # 不变

    def test_update_partial_fields(self, store):
        """只更新部分字段，其余保留"""
        result = store.save(content="内容", category="old", source="user", tags=["x"])
        mid = result["memory_id"]

        store.update(memory_id=mid, category="new", tags=["y"])

        mem = store.get(mid)
        assert mem["content"] == "内容"  # 不变
        assert mem["category"] == "new"  # 更新
        assert mem["source"] == "user"  # 不变
        assert mem["tags"] == ["y"]  # 更新

    def test_update_all_fields(self, store):
        """更新所有字段"""
        result = store.save(content="旧", category="a", sensitivity=10, source="x", tags=["1"])
        mid = result["memory_id"]

        store.update(memory_id=mid, content="新", category="b", sensitivity=50, source="y", tags=["2", "3"])

        mem = store.get(mid)
        assert mem["content"] == "新"
        assert mem["category"] == "b"
        assert mem["sensitivity"] == 50
        assert mem["source"] == "y"
        assert mem["tags"] == ["2", "3"]

    def test_update_nonexistent(self, store):
        """更新不存在的记忆应返回失败"""
        result = store.update(memory_id="non_existent_id", content="随便")
        assert result["success"] is False

    def test_update_sensitivity_clamping(self, store):
        """update 时 sensitivity 也应被钳制到 0-100"""
        result = store.save(content="敏感内容", sensitivity=5)
        mid = result["memory_id"]

        store.update(memory_id=mid, sensitivity=999)
        mem = store.get(mid)
        assert mem["sensitivity"] == 100

        store.update(memory_id=mid, sensitivity=-99)
        mem = store.get(mid)
        assert mem["sensitivity"] == 0

    def test_update_updates_timestamp(self, store):
        """update 应刷新 timestamp"""
        result = store.save(content="待更新")
        mid = result["memory_id"]
        old_ts = store.get(mid)["timestamp"]

        import time

        time.sleep(0.01)  # 确保时间有变化
        store.update(memory_id=mid, content="更新后")

        new_ts = store.get(mid)["timestamp"]
        assert new_ts > old_ts


@pytest.mark.skip(reason="chromadb Rust 后端在 Windows 上触发 access violation，需升级或替换")
class TestVectorSearch:
    """向量语义搜索测试"""

    @pytest.fixture
    def store(self, tmp_path):
        from core.storage import JsonStorage

        db_path = str(tmp_path / "vector_test.json")
        storage = JsonStorage(db_path)
        # Use a unique persist_dir per test to avoid HNSW index corruption
        # from shared ~/.alpha-id/chroma/Alpha_Vec_001 between test runs
        vector_dir = str(tmp_path / "chroma")
        return MemoryStore(
            alpha_id="Alpha-Vec-001",
            storage=storage,
            vector_persist_dir=vector_dir,
        )

    def test_semantic_query_basic(self, store):
        """语义搜索找到相关内容"""
        store.save(content="我喜欢喝咖啡")
        store.save(content="今天天气很好适合散步")
        store.save(content="Java是一种编程语言")
        results = store.query(query_text="咖啡因", limit=10)
        assert len(results) >= 1
        assert "咖啡" in results[0]["content"]

    def test_semantic_query_ordering(self, store):
        """相关性排序：更相关的结果在前"""
        store.save(content="Python是一种流行的编程语言")
        store.save(content="今天天气很好")
        store.save(content="我喜欢用Python写代码")
        results = store.query(query_text="Python编程", limit=10)
        assert len(results) >= 2
        # Python相关的结果应该排在前面
        first = results[0]["content"].lower()
        second = results[1]["content"].lower()
        assert "python" in first
        # 第二个可以是 天气 或 另一个Python

    def test_semantic_query_empty(self, store):
        """query_text为空时走原来的关键词搜索"""
        store.save(content="test content")
        store.save(content="other content")
        results = store.query(limit=10)
        assert len(results) == 2  # query_text 空，不走向量搜索

    def test_semantic_query_with_category_filter(self, store):
        """语义搜索 + 分类过滤"""
        store.save(content="机器学习是AI的一个分支", category="knowledge")
        store.save(content="今天和朋友吃了火锅", category="social")
        store.save(content="深度学习是机器学习的子集", category="knowledge")
        results = store.query(query_text="机器学习", category="knowledge", limit=10)
        assert len(results) == 2
        assert all(r["category"] == "knowledge" for r in results)

    def test_semantic_query_with_sensitivity_filter(self, store):
        """语义搜索 + 敏感度过滤"""
        store.save(content="公开的技术笔记", sensitivity=0)
        store.save(content="私密的日记内容", sensitivity=80)
        store.save(content="内部的技术文档", sensitivity=40)
        results = store.query(query_text="技术文档", max_sensitivity=50, limit=10)
        assert len(results) >= 1
        assert all(r["sensitivity"] <= 50 for r in results)

    def test_semantic_query_no_match(self, store):
        """语义搜索无匹配返回空列表"""
        store.save(content="今天天气很好")
        store.save(content="中午吃了什么")
        results = store.query(query_text="美国总统大选", limit=10)
        assert len(results) == 0

    def test_semantic_query_single_item(self, store):
        """单条记忆也能搜索"""
        store.save(content="量子计算的发展前景")
        results = store.query(query_text="量子计算机", limit=10)
        assert len(results) == 1

    def test_semantic_limit(self, store):
        """limit 限制在语义搜索中生效"""
        for i in range(5):
            store.save(content=f"编程语言第{i}条")
        results = store.query(query_text="编程", limit=3)
        assert len(results) == 3

    def test_semantic_chinese(self, store):
        """中文语义搜索"""
        store.save(content="苹果是一种水果")
        store.save(content="华为是一家科技公司")
        store.save(content="香蕉是黄色的")
        results = store.query(query_text="水果", limit=10)
        assert len(results) >= 1
        assert "水果" in results[0]["content"] or "香蕉" in results[0]["content"] or "苹果" in results[0]["content"]

    def test_keyword_still_works(self, store):
        """确认原来的关键词搜索没被破坏"""
        store.save(content="Python programming")
        store.save(content="Java programming")
        results = store.query(keyword="Python", limit=10)
        assert len(results) == 1

    def test_vector_index_rebuilds_on_new_save(self, store):
        """保存新记忆后，向量索引自动更新"""
        store.save(content="原始数据")
        r1 = store.query(query_text="数据", limit=10)
        store.save(content="新增的数据条目")
        r2 = store.query(query_text="数据", limit=10)
        assert len(r2) > len(r1)
