"""Tests for AID desktop fairy — command parsing & routing

注意：AidNuro 类依赖大量 GUI/硬件模块，测试时需要全面 mock。
"""

import pytest
import sys
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_all():
    """Mock tkinter and all hardware-dependent modules so AidNuro can be instantiated."""
    with patch.dict(
        sys.modules,
        {
            "tkinter": MagicMock(),
            "tools.screen_capture": MagicMock(),
            "tools.ocr": MagicMock(),
            "tools.window_control": MagicMock(),
            "core.memory_store": MagicMock(),
            "core.storage_sqlite": MagicMock(),
        },
    ):
        import tkinter as tk

        tk.Tk = MagicMock(return_value=MagicMock())
        tk.Toplevel = MagicMock(return_value=MagicMock())
        tk.Canvas = MagicMock(return_value=MagicMock())
        tk.Menu = MagicMock(return_value=MagicMock())
        tk.Frame = MagicMock(return_value=MagicMock())
        tk.Label = MagicMock(return_value=MagicMock())
        tk.Button = MagicMock(return_value=MagicMock())
        tk.Entry = MagicMock(return_value=MagicMock())
        tk.Text = MagicMock(return_value=MagicMock())
        tk.Scrollbar = MagicMock(return_value=MagicMock())

        canvas = tk.Canvas.return_value
        canvas.create_oval.return_value = 1
        canvas.create_arc.return_value = 2

        # 注意：daemon 模块使用下划线前缀的私有变量（_HAS_SCREEN 等）
        # 仅 patch 模块中实际存在的变量，并 mock 所有初始化步骤
        with (
            patch("entrypoints.daemon._HAS_SCREEN", True),
            patch("entrypoints.daemon._HAS_WINDOW", True),
            patch("entrypoints.daemon._HAS_MEMORY", False),
            patch("entrypoints.daemon._HAS_BRAIN", False),
            patch("entrypoints.daemon._HAS_VOICE", False),
            patch("entrypoints.daemon._HAS_OBSERVER", False),
            patch("entrypoints.daemon._HAS_POPUP", False),
            patch("entrypoints.daemon._HAS_DAILY", False),
            patch("entrypoints.daemon._HAS_CHARACTER", False),
            patch("entrypoints.daemon._HAS_IDENTITY", False),
            # mock 所有初始化方法，避免 GUI/硬件依赖
            patch.object(
                __import__("entrypoints.daemon", fromlist=["AidNuro"]).AidNuro,
                "_init_identity", return_value=None
            ),
            patch.object(
                __import__("entrypoints.daemon", fromlist=["AidNuro"]).AidNuro,
                "_init_memory", return_value=None
            ),
            patch.object(
                __import__("entrypoints.daemon", fromlist=["AidNuro"]).AidNuro,
                "_init_brain", return_value=None
            ),
            patch.object(
                __import__("entrypoints.daemon", fromlist=["AidNuro"]).AidNuro,
                "_init_voice", return_value=None
            ),
            patch.object(
                __import__("entrypoints.daemon", fromlist=["AidNuro"]).AidNuro,
                "_init_observer", return_value=None
            ),
        ):
            from entrypoints.daemon import AidNuro as AIDFairy

            fairy = AIDFairy(no_mcp=True, no_brain=True)
            fairy._show_result = MagicMock()
            yield fairy


class TestParseAndClick:
    """_parse_and_click coordinate extraction"""

    def test_extract_two_numbers(self, mock_all):
        fairy = mock_all
        fairy._parse_and_click("点击 500 300")
        fairy._show_result.assert_called_once()
        msg = fairy._show_result.call_args[0][0]
        assert "500" in msg and "300" in msg

    def test_insufficient_numbers(self, mock_all):
        fairy = mock_all
        fairy._parse_and_click("点击 500")
        fairy._show_result.assert_called_once_with("用法：点击 x y\n例如：点击 500 300")

    def test_no_numbers(self, mock_all):
        fairy = mock_all
        fairy._parse_and_click("点这里")
        fairy._show_result.assert_called_once_with("用法：点击 x y\n例如：点击 500 300")


class TestParseAndType:
    """_parse_and_type text extraction"""

    def test_extract_after_input(self, mock_all):
        fairy = mock_all
        fairy._parse_and_type("输入 你好世界")
        fairy._show_result.assert_called_once()
        msg = fairy._show_result.call_args[0][0]
        assert "你好世界" in msg

    def test_extract_after_da(self, mock_all):
        fairy = mock_all
        fairy._parse_and_type("da 你好世界")
        fairy._show_result.assert_called_once()
        msg = fairy._show_result.call_args[0][0]
        assert "你好世界" in msg

    def test_empty_text_no_prefix(self, mock_all):
        fairy = mock_all
        fairy._parse_and_type("你好世界")
        fairy._show_result.assert_called_once_with("用法：输入 你想说的话\n例如：输入 你好世界")


class TestProcessCommand:
    """_process_command routing"""

    def test_screenshot_keyword(self, mock_all):
        fairy = mock_all
        fairy._process_command("看屏幕")
        fairy._show_result.assert_called_once()

    def test_window_keyword(self, mock_all):
        fairy = mock_all
        fairy._process_command("窗口列表")
        fairy._show_result.assert_called_once()

    def test_mouse_keyword(self, mock_all):
        fairy = mock_all
        fairy._process_command("鼠标位置")
        fairy._show_result.assert_called_once()

    def test_click_keyword(self, mock_all):
        fairy = mock_all
        fairy._process_command("点击 100 200")
        fairy._show_result.assert_called_once()
        msg = fairy._show_result.call_args[0][0]
        assert "100" in msg and "200" in msg

    def test_type_keyword(self, mock_all):
        fairy = mock_all
        fairy._process_command("输入 hello")
        fairy._show_result.assert_called_once()
        msg = fairy._show_result.call_args[0][0]
        assert "hello" in msg

    def test_identity_keyword(self, mock_all):
        fairy = mock_all
        fairy._process_command("身份")
        fairy._show_result.assert_called_once()

    def test_unknown_command(self, mock_all):
        fairy = mock_all
        fairy._process_command("xyzabc")
        fairy._show_result.assert_called_once_with("不懂指令，请说：看屏幕 / 窗口列表 / 鼠标位置 / 点击 x y / 输入 文字")

    def test_empty_command(self, mock_all):
        fairy = mock_all
        fairy._process_command("")
        fairy._show_result.assert_not_called()

    def test_whitespace_command(self, mock_all):
        fairy = mock_all
        fairy._process_command("   ")
        fairy._show_result.assert_not_called()

    def test_case_insensitive(self, mock_all):
        fairy = mock_all
        fairy._process_command("SCREENSHOT")
        fairy._show_result.assert_called_once()

    def test_english_screenshot(self, mock_all):
        fairy = mock_all
        fairy._process_command("screenshot")
        fairy._show_result.assert_called_once()

    def test_partial_match_type(self, mock_all):
        fairy = mock_all
        fairy._process_command("打 hello")
        fairy._show_result.assert_called_once()
        msg = fairy._show_result.call_args[0][0]
        assert "hello" in msg
