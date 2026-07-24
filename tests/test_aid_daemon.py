"""Tests for AID desktop fairy — command parsing & routing"""

import pytest
import sys
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_all():
    """Mock tkinter and all hardware-dependent modules so AIDFairy can be instantiated."""
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

        with (
            patch("entrypoints.daemon.HAS_SCREEN", True),
            patch("entrypoints.daemon.HAS_WINDOW", True),
            patch("entrypoints.daemon.HAS_OCR", True),
            patch("entrypoints.daemon.HAS_MEMORY", False),
            patch("entrypoints.daemon.HAS_LLM", False),
            patch("entrypoints.daemon.HAS_TTS", False),
            patch("entrypoints.daemon.HAS_SPEECH_RECOGNITION", False),
        ):
            from entrypoints.daemon import AIDFairy

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
        fairy._parse_and_type("打 hello")
        fairy._show_result.assert_called_once()
        msg = fairy._show_result.call_args[0][0]
        assert "hello" in msg

    def test_empty_text_no_prefix(self, mock_all):
        fairy = mock_all
        fairy._parse_and_type("类型")
        fairy._show_result.assert_called_once_with("用法：输入 你想说的话\n例如：输入 你好世界")


class TestProcessCommand:
    """_process_command keyword routing"""

    def test_screenshot_keyword(self, mock_all):
        fairy = mock_all
        with patch.object(fairy, "_quick_look_result") as mock_method:
            fairy._process_command("看屏幕")
            mock_method.assert_called_once()

    def test_window_keyword(self, mock_all):
        fairy = mock_all
        with patch.object(fairy, "_list_windows_result") as mock_method:
            fairy._process_command("窗口列表")
            mock_method.assert_called_once()

    def test_mouse_keyword(self, mock_all):
        fairy = mock_all
        with patch.object(fairy, "_mouse_position_result") as mock_method:
            fairy._process_command("鼠标位置")
            mock_method.assert_called_once()

    def test_click_keyword(self, mock_all):
        fairy = mock_all
        with patch.object(fairy, "_parse_and_click") as mock_method:
            fairy._process_command("点击 100 200")
            mock_method.assert_called_once_with("点击 100 200")

    def test_type_keyword(self, mock_all):
        fairy = mock_all
        with patch.object(fairy, "_parse_and_type") as mock_method:
            fairy._process_command("输入 hello")
            mock_method.assert_called_once_with("输入 hello")

    def test_identity_keyword(self, mock_all):
        fairy = mock_all
        with patch.object(fairy, "_show_identity") as mock_method:
            fairy._process_command("身份信息")
            mock_method.assert_called_once()

    def test_unknown_command(self, mock_all):
        fairy = mock_all
        fairy._process_command("今天天气怎么样")
        fairy._show_result.assert_called_once()
        msg = fairy._show_result.call_args[0][0]
        assert "不懂指令" in msg

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
        with patch.object(fairy, "_quick_look_result") as mock_method:
            fairy._process_command("SCREENSHOT")
            mock_method.assert_called_once()

    def test_english_screenshot(self, mock_all):
        fairy = mock_all
        with patch.object(fairy, "_quick_look_result") as mock_method:
            fairy._process_command("screenshot")
            mock_method.assert_called_once()

    def test_partial_match_type(self, mock_all):
        fairy = mock_all
        with patch.object(fairy, "_parse_and_type") as mock_method:
            fairy._process_command("帮我输入 测试文字")
            mock_method.assert_called_once()
