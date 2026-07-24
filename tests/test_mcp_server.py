"""
全面测试 MCP Server 的全部 ~30 个工具。

策略：
- 错误路径：monkeypatch HAS_* = False，测降级提示
- Codex 工具（纯 Python）：在临时目录直接测
- MemoryGraph 工具：mock store 层
"""

import os
import json
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest
import aid_mcp_server


# ═══════════════════════════════════════════════
#  错误路径：HAS_* = False 时的降级
#  注意：memory_graph 工具定义在 if HAS_MEMORY_GRAPH: 块内，
#  没有运行时守卫，所以 monkeypatch 不影响它们。
# ═══════════════════════════════════════════════


class TestScreenCaptureUnavailable:
    """HAS_SCREEN_CAPTURE = False 时，截图工具返回错误提示"""

    @pytest.fixture(autouse=True)
    def patch_no_screen(self, monkeypatch):
        monkeypatch.setattr(aid_mcp_server, "HAS_SCREEN_CAPTURE", False)

    def test_capture_full_screen(self):
        r = aid_mcp_server.capture_full_screen()
        assert "❌" in r and "截图工具" in r

    def test_capture_window(self):
        r = aid_mcp_server.capture_window("Test")
        assert "❌" in r and "截图工具" in r

    def test_capture_region(self):
        r = aid_mcp_server.capture_region(0, 0, 100, 100)
        assert "❌" in r and "截图工具" in r

    def test_list_windows(self):
        r = aid_mcp_server.list_windows()
        assert "❌" in r and "截图工具" in r


class TestOcrUnavailable:
    """HAS_OCR = False 时，OCR 工具返回错误提示"""

    @pytest.fixture(autouse=True)
    def patch_no_ocr(self, monkeypatch):
        monkeypatch.setattr(aid_mcp_server, "HAS_OCR", False)

    def test_ocr_image(self):
        r = aid_mcp_server.ocr_image("nonexistent.png")
        assert "❌" in r and "OCR" in r

    def test_analyze_image(self):
        r = aid_mcp_server.analyze_image("nonexistent.png")
        assert "❌" in r and ("视觉分析" in r or "OCR" in r)


class TestWindowControlUnavailable:
    """HAS_WINDOW_CONTROL = False 时，窗口控制工具返回错误提示"""

    @pytest.fixture(autouse=True)
    def patch_no_wc(self, monkeypatch):
        monkeypatch.setattr(aid_mcp_server, "HAS_WINDOW_CONTROL", False)

    def test_focus_window(self):
        r = aid_mcp_server.focus_window("Test")
        assert "❌" in r and "窗口控制" in r

    def test_click_screen(self):
        r = aid_mcp_server.click_screen(100, 200)
        assert "❌" in r and "窗口控制" in r

    def test_click_double(self):
        r = aid_mcp_server.click_double(100, 200)
        assert "❌" in r and "窗口控制" in r

    def test_click_right(self):
        r = aid_mcp_server.click_right(100, 200)
        assert "❌" in r and "窗口控制" in r

    def test_type_text(self):
        r = aid_mcp_server.type_text("hello")
        assert "❌" in r and "窗口控制" in r

    def test_type_at(self):
        r = aid_mcp_server.type_at("hello", 100, 200)
        assert "❌" in r and "窗口控制" in r

    def test_press_key(self):
        r = aid_mcp_server.press_key("enter")
        assert "❌" in r and "窗口控制" in r

    def test_press_enter(self):
        r = aid_mcp_server.press_enter()
        assert "❌" in r and "窗口控制" in r

    def test_scroll(self):
        r = aid_mcp_server.scroll()
        assert "❌" in r and "窗口控制" in r

    def test_mouse_position(self):
        r = aid_mcp_server.mouse_position()
        assert "❌" in r and "窗口控制" in r


class TestIdentityUnavailable:
    """HAS_IDENTITY = False 时"""

    @pytest.fixture(autouse=True)
    def patch_no_id(self, monkeypatch):
        monkeypatch.setattr(aid_mcp_server, "HAS_IDENTITY", False)

    def test_get_identity(self):
        r = aid_mcp_server.get_identity()
        assert "❌" in r or "未初始化" in r or "不可用" in r

    def test_get_server_info(self):
        """get_server_info 没有 HAS_* 守卫，应返回完整能力列表"""
        r = aid_mcp_server.get_server_info()
        assert "AID MCP Server" in r
        assert "可用能力" in r


# ═══════════════════════════════════════════════
#  Codex 工具（纯 Python，无需硬件）
# ═══════════════════════════════════════════════


class TestCodexTools:
    """codex.py 是纯 Python 工具，可在临时目录下直接测试"""

    @pytest.fixture
    def tmp_workspace(self):
        """创建临时工作目录并切换 codex WORKSPACE"""
        from pathlib import Path
        import codex  # 模块级 WORKSPACE (Path 对象)

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            old_workspace = codex.WORKSPACE
            os.chdir(tmpdir)
            codex.WORKSPACE = Path(tmpdir)
            # 创建测试文件
            test_file = os.path.join(tmpdir, "hello.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("# hello\nprint('hello world')\n")
            yield tmpdir
            os.chdir(old_cwd)
            codex.WORKSPACE = old_workspace

    def test_read_code(self, tmp_workspace):
        path = os.path.join(tmp_workspace, "hello.py")
        r = aid_mcp_server.read_code(path)
        assert "hello.py" in r
        assert "hello world" in r
        assert "lines" in r

    def test_read_code_not_found(self, tmp_workspace):
        r = aid_mcp_server.read_code(os.path.join(tmp_workspace, "nope.py"))
        assert "not found" in r.lower()

    def test_search_code(self, tmp_workspace):
        r = aid_mcp_server.search_code("hello")
        assert "Found" in r or "hello.py" in r

    def test_search_code_no_match(self, tmp_workspace):
        r = aid_mcp_server.search_code("xyzzy_does_not_exist_42")
        assert "No matches" in r

    def test_edit_code(self, tmp_workspace):
        path = os.path.join(tmp_workspace, "hello.py")
        r = aid_mcp_server.edit_code(path, "hello world", "world hello")
        assert "OK" in r or "Replace" in r
        with open(path, encoding="utf-8") as f:
            assert "world hello" in f.read()

    def test_edit_code_not_found(self, tmp_workspace):
        r = aid_mcp_server.edit_code(os.path.join(tmp_workspace, "nope.py"), "a", "b")
        assert "not found" in r.lower()

    def test_edit_code_string_not_found(self, tmp_workspace):
        r = aid_mcp_server.edit_code(os.path.join(tmp_workspace, "hello.py"), "not_there_42", "b")
        assert "not found" in r

    def test_run_python(self):
        r = aid_mcp_server.run_python("print(2+2)")
        assert "4" in r

    def test_run_python_error(self):
        r = aid_mcp_server.run_python("1/0")
        assert "ZeroDivisionError" in r

    def test_list_code_files(self, tmp_workspace):
        r = aid_mcp_server.list_code_files(path=tmp_workspace, pattern="*.py")
        assert "hello.py" in r

    def test_list_code_files_no_match(self, tmp_workspace):
        r = aid_mcp_server.list_code_files(path=tmp_workspace, pattern="*.js")
        assert "No" in r or "0" in r or "（空）" in r

    def test_count_code_lines(self, tmp_workspace):
        r = aid_mcp_server.count_code_lines(path=tmp_workspace)
        assert "Total" in r or "total" in r.lower()
        assert "hello.py" in r

    def test_count_code_lines_empty_dir(self, tmp_workspace):
        empty = os.path.join(tmp_workspace, "empty_sub")
        os.makedirs(empty, exist_ok=True)
        r = aid_mcp_server.count_code_lines(path=empty)
        assert "Total" in r or "0" in r


# ═══════════════════════════════════════════════
#  MemoryGraph 工具（mock 数据层）
# ═══════════════════════════════════════════════
# 这些工具在 if HAS_MEMORY_GRAPH: 块内定义，无运行时守卫，
# 所以需要 mock memory_graph 模块内部的依赖。


class TestMemoryGraphTools:
    """Mock MemoryStore/SqliteStorage 来测试记忆网络工具"""

    def test_memory_graph_save_no_content(self):
        """不传 content 应报错"""
        r = aid_mcp_server.memory_graph_save(content="")
        assert "Error" in r or "请提供" in r

    def test_memory_graph_delete_no_id(self):
        """不传 memory_id 应报错"""
        r = aid_mcp_server.memory_graph_delete(memory_id="")
        assert "Error" in r or "请提供" in r

    def test_memory_graph_update_no_id(self):
        """不传 memory_id 应报错"""
        r = aid_mcp_server.memory_graph_update(memory_id="")
        assert "Error" in r or "请提供" in r

    def test_memory_graph_stats_mock(self):
        """mock MemoryStore.query 返回空列表"""
        with patch("memory_graph.SqliteStorage") as mock_storage, patch("memory_graph.MemoryStore") as mock_store:
            fake_store = Mock()
            fake_store.query.return_value = []
            mock_storage.return_value = MagicMock()
            mock_store.return_value = fake_store
            r = aid_mcp_server.memory_graph_stats("Alpha-001")
            assert isinstance(r, str)

    def test_memory_graph_search_mock(self):
        """mock 搜索"""
        with patch("memory_graph.SqliteStorage") as mock_storage, patch("memory_graph.MemoryStore") as mock_store:
            fake_store = Mock()
            fake_store.query.return_value = []
            mock_storage.return_value = MagicMock()
            mock_store.return_value = fake_store
            r = aid_mcp_server.memory_graph_search("Alpha-001", query="test")
            assert isinstance(r, str)

    def test_memory_graph_html_mock(self):
        """mock html 生成"""
        with patch("memory_graph.SqliteStorage") as mock_storage, patch("memory_graph.MemoryStore") as mock_store:
            fake_store = Mock()
            fake_store.query.return_value = []
            mock_storage.return_value = MagicMock()
            mock_store.return_value = fake_store
            r = aid_mcp_server.memory_graph_html("Alpha-001")
            assert isinstance(r, str)

    def test_memory_graph_save_mock(self):
        """mock 保存"""
        with patch("memory_graph.SqliteStorage") as mock_storage, patch("memory_graph.MemoryStore") as mock_store:
            fake_store = Mock()
            fake_store.save.return_value = {"memory_id": "mock-123"}
            mock_storage.return_value = MagicMock()
            mock_store.return_value = fake_store
            r = aid_mcp_server.memory_graph_save(content="test content")
            assert isinstance(r, str) and "OK" in r

    def test_memory_graph_delete_mock(self):
        """mock 删除"""
        with patch("memory_graph.SqliteStorage") as mock_storage, patch("memory_graph.MemoryStore") as mock_store:
            fake_store = Mock()
            fake_store.delete.return_value = {"memory_id": "mock-123"}
            mock_storage.return_value = MagicMock()
            mock_store.return_value = fake_store
            r = aid_mcp_server.memory_graph_delete(memory_id="test-id")
            assert isinstance(r, str)

    def test_memory_graph_update_mock(self):
        """mock 更新"""
        with patch("memory_graph.SqliteStorage") as mock_storage, patch("memory_graph.MemoryStore") as mock_store:
            fake_store = Mock()
            fake_store.update.return_value = {"success": True}
            mock_storage.return_value = MagicMock()
            mock_store.return_value = fake_store
            r = aid_mcp_server.memory_graph_update(memory_id="test-id", content="new")
            assert isinstance(r, str)


# ═══════════════════════════════════════════════
#  工具注册完整性
# ═══════════════════════════════════════════════


@pytest.mark.asyncio
async def test_all_tools_listed():
    """确保所有 ~30 个工具都正确注册"""
    tools = await aid_mcp_server.mcp.list_tools()
    names = [t.name for t in tools]
    expected = [
        "capture_full_screen",
        "capture_window",
        "capture_region",
        "list_windows",
        "ocr_image",
        "analyze_image",
        "focus_window",
        "click_screen",
        "click_double",
        "click_right",
        "type_text",
        "type_at",
        "press_key",
        "press_enter",
        "scroll",
        "mouse_position",
        "get_identity",
        "verify_identity",
        "get_server_info",
        "read_code",
        "search_code",
        "edit_code",
        "run_python",
        "list_code_files",
        "count_code_lines",
        "memory_graph_stats",
        "memory_graph_html",
        "memory_graph_search",
        "memory_graph_save",
        "memory_graph_delete",
        "memory_graph_update",
    ]
    for name in expected:
        assert name in names, f"缺少工具: {name}"
    assert len(names) == len(expected), f"预期 {len(expected)} 个工具，实际 {len(names)} 个"
