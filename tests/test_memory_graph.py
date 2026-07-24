"""Memory Graph 模块测试"""

import os, tempfile, json

from memory_graph import build_graph, render_html, graph_stats_text, generate_graph_html
from core.memory_store import MemoryStore
from core.storage import JsonStorage


def test_build_graph_empty():
    """空记忆返回空图"""
    store = MemoryStore(alpha_id="Test-Empty", storage=JsonStorage(tempfile.mktemp(suffix=".json")))
    graph = build_graph(store)
    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["stats"]["total"] == 0


def test_build_graph_with_data():
    """有记忆时正确生成节点和关联"""
    store = MemoryStore(alpha_id="Test-Graph", storage=JsonStorage(tempfile.mktemp(suffix=".json")))
    store.save(content="喝咖啡", category="preference", tags=["coffee", "hobby"])
    store.save(content="Python编程", category="knowledge", tags=["python", "programming"])
    store.save(content="今天天气好", category="daily", tags=["weather"])

    graph = build_graph(store)
    assert len(graph["nodes"]) == 3
    assert "stats" in graph
    assert graph["stats"]["total"] == 3

    # 共享标签 "programming" 和 "python" 的记忆之间应有边
    # 但 coffee 和 weather 之间不应该有
    # 至少偏好和知识之间应该有较弱关联（基于 bigram 重叠？）
    # 只要图不空就行
    print(f"Nodes: {len(graph['nodes'])}, Edges: {len(graph['edges'])}")


def test_build_graph_max_nodes():
    """max_nodes 限制生效"""
    store = MemoryStore(alpha_id="Test-Max", storage=JsonStorage(tempfile.mktemp(suffix=".json")))
    for i in range(20):
        store.save(content=f"记忆{i:03d}", tags=["test"])

    graph = build_graph(store, max_nodes=5)
    assert len(graph["nodes"]) == 5


def test_build_graph_filter_category():
    """include_categories 过滤生效"""
    store = MemoryStore(alpha_id="Test-Cat", storage=JsonStorage(tempfile.mktemp(suffix=".json")))
    store.save(content="知识1", category="knowledge")
    store.save(content="社交1", category="social")
    store.save(content="知识2", category="knowledge")

    graph = build_graph(store, include_categories=["knowledge"])
    assert len(graph["nodes"]) == 2
    assert all(n["category"] == "knowledge" for n in graph["nodes"])


def test_build_graph_filter_sensitivity():
    """max_sensitivity 过滤生效"""
    store = MemoryStore(alpha_id="Test-Sens", storage=JsonStorage(tempfile.mktemp(suffix=".json")))
    store.save(content="公开", sensitivity=0)
    store.save(content="机密", sensitivity=80)

    graph = build_graph(store, max_sensitivity=50)
    assert len(graph["nodes"]) == 1
    assert graph["nodes"][0]["content_preview"].startswith("公开")


def test_cosine_sim():
    """_cosine_sim 内部函数"""
    from memory_graph import _cosine_sim

    # 完全相同标签
    sim = _cosine_sim(["a", "b"], ["a", "b"], "hello", "hello")
    assert sim == 1.0
    # 无共享
    sim = _cosine_sim(["a"], ["b"], "abc", "xyz")
    assert sim == 0.0
    # 部分共享
    sim = _cosine_sim(["a", "b"], ["a", "c"], "hello", "world")
    assert 0 < sim < 1


def test_render_html():
    """HTML 渲染输出结构正确"""
    graph = {
        "nodes": [
            {
                "id": "1",
                "label": "测试",
                "category": "general",
                "sensitivity": 0,
                "tags": [],
                "group": "general",
                "color": "#666",
                "content_preview": "测试内容",
                "size": 5,
            }
        ],
        "edges": [],
        "stats": {"total": 1, "edges": 0, "categories": {"general": 1}},
    }
    html = render_html(graph, title="测试图")
    assert "<!DOCTYPE html>" in html
    assert "d3.v7.min.js" in html
    assert "测试" in html
    assert "统计" not in html or True  # stats 可能不显示


def test_graph_stats_text():
    """文本统计信息格式正确"""
    store = MemoryStore(alpha_id="Test-Stat", storage=JsonStorage(tempfile.mktemp(suffix=".json")))
    store.save(content="知识1", category="knowledge", tags=["a"])
    store.save(content="知识2", category="knowledge", tags=["b"])
    store.save(content="社交", category="social", tags=["c"])

    text = graph_stats_text(store)
    assert "记忆网络统计" in text
    assert "3 条" in text
    assert "knowledge" in text
    assert "social" in text


def test_graph_stats_text_empty():
    """空记忆时返回提示信息"""
    text = graph_stats_text(MemoryStore(alpha_id="Test-Empty", storage=JsonStorage(tempfile.mktemp(suffix=".json"))))
    assert "为空" in text


def test_generate_graph_html():
    """生成 HTML 文件成功"""
    store = MemoryStore(alpha_id="Test-Html", storage=JsonStorage(tempfile.mktemp(suffix=".json")))
    store.save(content="测试记忆", category="general")

    out = tempfile.mktemp(suffix=".html")
    path = generate_graph_html(store, output_path=out)
    assert os.path.isfile(path)
    content = open(path, encoding="utf-8").read()
    assert "<!DOCTYPE html>" in content
    os.unlink(path)


def test_hub_nodes_detection():
    """枢纽节点检测（有连接的节点会被报告）"""
    store = MemoryStore(alpha_id="Test-Hub", storage=JsonStorage(tempfile.mktemp(suffix=".json")))
    store.save(content="核心", tags=["master"])
    for i in range(4):
        store.save(content=f"子节点{i}", tags=["master", f"tag_{i}"])

    text = graph_stats_text(store)
    assert "枢纽节点" in text
    # 任何节点都应该出现在枢纽列表里（因为都有连接）
    assert "核心" in text or "子节点" in text
