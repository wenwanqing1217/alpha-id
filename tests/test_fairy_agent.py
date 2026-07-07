"""Tests for fairy_agent.py — FairyTool + FairyBrain (no LLM API key needed)."""

from unittest.mock import MagicMock, patch

import pytest

from fairy_agent import HAS_OPENAI, FairyBrain, FairyTool

# ═══════════════════════════════════════════════
# FairyTool tests
# ═══════════════════════════════════════════════


class TestFairyTool:
    def test_basic(self):
        fn = MagicMock(return_value="hello")
        t = FairyTool("greet", "say hello", {"type": "object", "properties": {}, "required": []}, fn)
        assert t.name == "greet"
        assert t.description == "say hello"

    def test_to_openai_tool(self):
        fn = MagicMock()
        params = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
        t = FairyTool("click", "do click", params, fn)
        out = t.to_openai_tool()
        assert out["type"] == "function"
        assert out["function"]["name"] == "click"
        assert out["function"]["parameters"] == params

    def test_call_returns_result(self):
        fn = MagicMock(return_value="done")
        t = FairyTool("test", "desc", {"type": "object", "properties": {}, "required": []}, fn)
        result = t(x=1)
        assert result == "done"
        fn.assert_called_once_with(x=1)

    def test_call_none_result(self):
        fn = MagicMock(return_value=None)
        t = FairyTool("test", "desc", {"type": "object", "properties": {}, "required": []}, fn)
        result = t()
        assert result == "（执行成功，无返回）"

    def test_call_raises_exception(self):
        fn = MagicMock(side_effect=ValueError("oops"))
        t = FairyTool("test", "desc", {"type": "object", "properties": {}, "required": []}, fn)
        result = t()
        assert "[工具执行失败]" in result
        assert "oops" in result


# ═══════════════════════════════════════════════
# FairyBrain tests
# ═══════════════════════════════════════════════


class MockFairy:
    """Stub for the fairy GUI object that FairyBrain depends on."""

    def __init__(self):
        self.shown = []

    def _show_result(self, text):
        self.shown.append(text)

    def _quick_look(self):
        pass

    def _list_windows(self):
        pass

    def _show_mouse_position(self):
        pass

    def _parse_and_click(self, cmd):
        pass

    def _parse_and_type(self, cmd):
        pass

    def _show_identity(self):
        pass


class MockMemory:
    """Stub memory store for testing context loading."""

    def __init__(self, results=None):
        self.results = results or []
        self.saved = []

    def query(self, keyword="", category="", limit=5):
        return self.results

    def save(self, **kwargs):
        self.saved.append(kwargs)


class TestFairyBrainInit:
    """Test __init__ and property access."""

    def test_init_no_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        brain = FairyBrain(MockFairy())
        assert brain.api_key == ""
        assert brain.api_base == ""
        assert brain.model == "gpt-4o-mini"
        assert brain._client is None
        # 8 tools registered
        assert len(brain.tools) == 8

    def test_init_with_env(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_API_BASE", "https://example.com/v1")
        monkeypatch.setenv("AID_LLM_MODEL", "gpt-4")
        brain = FairyBrain(MockFairy())
        assert brain.api_key == "sk-test"
        assert brain.api_base == "https://example.com/v1"
        assert brain.model == "gpt-4"

    def test_available_false_no_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        assert brain.available is False

    def test_available_true(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        brain = FairyBrain(MockFairy())
        assert brain.available == HAS_OPENAI  # True if openai installed

    def test_client_property_creates_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_API_BASE", "https://example.com/v1")
        brain = FairyBrain(MockFairy())
        brain._client = None  # force re-create
        with patch("fairy_agent.OpenAI") as mock_openai:
            client = brain.client
            mock_openai.assert_called_once_with(api_key="sk-test", base_url="https://example.com/v1")
            assert client is not None

    def test_client_property_no_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        assert brain.client is None

    def test_add_tool(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        count_before = len(brain.tools)
        new = FairyTool("custom", "desc", {"type": "object", "properties": {}, "required": []}, MagicMock())
        brain._add_tool(new)
        assert len(brain.tools) == count_before + 1
        assert brain.tools["custom"] is new


class TestFairyBrainProcess:
    def test_empty_cmd_returns_dot(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        assert brain.process("") == "嗯？"
        assert brain.process("  ") == "嗯？"

    def test_unavailable_returns_none(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        result = brain.process("hello")
        assert result is None


class TestFairyBrainMemory:
    def test_load_past_context_no_memory(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        assert not hasattr(brain, "_ctx_summary") or brain._ctx_summary == ""

    def test_load_past_context_with_empty_memory(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        brain.memory = MockMemory(results=[])
        brain._load_past_context()
        assert brain._ctx_summary == ""

    def test_load_past_context_with_content(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        brain.memory = MockMemory(results=[{"content": "用户说: hello → AID: hi"}])
        brain._load_past_context()
        assert "上次聊过的话题" in brain._ctx_summary
        assert "hello" in brain._ctx_summary

    def test_load_past_context_exception_handled(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        err_memory = MagicMock()
        err_memory.query.side_effect = RuntimeError("db error")
        brain.memory = err_memory
        brain._load_past_context()
        assert brain._ctx_summary == ""

    def test_remember_no_memory(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        brain.memory = None
        # should not raise
        brain._remember("hello", "world")
        assert True

    def test_remember_with_memory(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        memory = MockMemory()
        brain.memory = memory
        brain._remember("hello", "world")
        assert len(memory.saved) == 1
        assert "hello" in memory.saved[0]["content"]
        assert "world" in memory.saved[0]["content"]

    def test_remember_exception_handled(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        brain = FairyBrain(MockFairy())
        err_memory = MagicMock()
        err_memory.save.side_effect = RuntimeError("save error")
        brain.memory = err_memory
        brain._remember("hello", "world")  # should not raise
        assert True


class TestFairyBrainCallLlm:
    """_call_llm with mocked OpenAI client."""

    def _make_mock_chat(self, content=None, tool_calls=None):
        """Build a mock chat completion response."""
        choice = MagicMock()
        choice.message.content = content
        choice.message.tool_calls = tool_calls
        response = MagicMock()
        response.choices = [choice]
        return response

    def test_api_error_returns_message(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        brain = FairyBrain(MockFairy())
        brain._client = MagicMock()
        brain._client.chat.completions.create.side_effect = Exception("connection refused")
        result = brain._call_llm("hello")
        assert "不可用" in result
        assert "connection refused" in result

    def test_simple_reply(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        brain = FairyBrain(MockFairy())
        brain._client = MagicMock()
        brain._client.chat.completions.create.return_value = self._make_mock_chat(content="Hi there!")
        result = brain._call_llm("hello")
        assert result == "Hi there!"
        assert len(brain.history) == 2  # user + assistant

    def test_with_context_summary(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        brain = FairyBrain(MockFairy())
        brain._ctx_summary = "上次聊了天气"
        brain._client = MagicMock()
        brain._client.chat.completions.create.return_value = self._make_mock_chat(content="是的，天气不错")
        result = brain._call_llm("天气怎么样")
        assert "天气不错" in result

    def test_tool_call_flow(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        brain = FairyBrain(MockFairy())
        brain._client = MagicMock()

        tc = MagicMock()
        tc.id = "call_1"
        tc.function.name = "quick_look"
        tc.function.arguments = "{}"

        # First response: tool call, Second response: final reply
        brain._client.chat.completions.create.side_effect = [
            self._make_mock_chat(tool_calls=[tc]),
            self._make_mock_chat(content="屏幕上有个窗口"),
        ]

        result = brain._call_llm("看看屏幕")
        assert "屏幕上" in result
        assert brain._client.chat.completions.create.call_count == 2

    def test_tool_unknown(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        brain = FairyBrain(MockFairy())
        brain._client = MagicMock()

        tc = MagicMock()
        tc.id = "call_2"
        tc.function.name = "nonexistent_tool"
        tc.function.arguments = "{}"

        brain._client.chat.completions.create.side_effect = [
            self._make_mock_chat(tool_calls=[tc]),
            self._make_mock_chat(content="没找到工具"),
        ]

        result = brain._call_llm("do something")
        assert "没找到" in result

    def test_tool_json_decode_error(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        brain = FairyBrain(MockFairy())
        brain._client = MagicMock()

        tc = MagicMock()
        tc.id = "call_3"
        tc.function.name = "quick_look"
        tc.function.arguments = "not-json{{{"

        brain._client.chat.completions.create.side_effect = [
            self._make_mock_chat(tool_calls=[tc]),
            self._make_mock_chat(content="done"),
        ]

        result = brain._call_llm("test")
        assert result == "done"

    def test_max_turns_exceeded(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        brain = FairyBrain(MockFairy())
        brain._client = MagicMock()

        tc = MagicMock()
        tc.id = "call_x"
        tc.function.name = "quick_look"
        tc.function.arguments = "{}"

        # Always respond with a tool call → infinite loop capped at 5
        brain._client.chat.completions.create.return_value = self._make_mock_chat(tool_calls=[tc])

        result = brain._call_llm("test")
        assert "思考太久" in result


class TestFairyBrainRegisterTools:
    """Test the _register_tools inner closure functions."""

    @pytest.fixture
    def brain(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        return FairyBrain(MockFairy())

    def test_quick_look_ok(self, brain):
        tool = brain.tools["quick_look"]
        result = tool()
        assert "查看屏幕" in result

    def test_quick_look_not_ready(self, brain):
        brain.fairy = object()  # no _quick_look method
        tool = brain.tools["quick_look"]
        result = tool()
        assert "未就绪" in result

    def test_list_windows_ok(self, brain):
        tool = brain.tools["list_windows"]
        result = tool()
        assert "当前打开的窗口列表" in result

    def test_list_windows_not_ready(self, brain):
        brain.fairy = object()
        tool = brain.tools["list_windows"]
        result = tool()
        assert "未就绪" in result

    def test_mouse_position_ok(self, brain):
        tool = brain.tools["mouse_position"]
        result = tool()
        assert "鼠标当前位于屏幕坐标" in result

    def test_mouse_position_not_ready(self, brain):
        brain.fairy = object()
        tool = brain.tools["mouse_position"]
        result = tool()
        assert "未就绪" in result

    def test_click_ok(self, brain):
        tool = brain.tools["click"]
        result = tool(x=100, y=200)
        assert "已点击" in result

    def test_click_not_ready(self, brain):
        brain.fairy = object()
        tool = brain.tools["click"]
        result = tool(x=100, y=200)
        assert "未就绪" in result

    def test_type_text_ok(self, brain):
        tool = brain.tools["type_text"]
        result = tool(text="hello")
        assert "已输入" in result

    def test_type_text_not_ready(self, brain):
        brain.fairy = object()
        tool = brain.tools["type_text"]
        result = tool(text="hello")
        assert "未就绪" in result

    def test_show_identity_ok(self, brain):
        tool = brain.tools["show_identity"]
        result = tool()
        assert "AID 身份" in result

    def test_show_identity_not_ready(self, brain):
        brain.fairy = object()
        tool = brain.tools["show_identity"]
        result = tool()
        assert "未就绪" in result

    def test_save_memory_with_memory(self, brain):
        memory = MockMemory()
        brain.memory = memory
        tool = brain.tools["save_memory"]
        result = tool(content="remember this", category="用户偏好")
        assert "已记住" in result
        assert len(memory.saved) == 1
        assert memory.saved[0]["content"] == "remember this"

    def test_save_memory_no_memory(self, brain):
        brain.memory = None
        tool = brain.tools["save_memory"]
        result = tool(content="test", category="对话记录")
        assert "未就绪" in result

    def test_query_memory_with_results(self, brain):
        memory = MockMemory(results=[{"content": "something important"}])
        brain.memory = memory
        tool = brain.tools["query_memory"]
        result = tool(keyword="test")
        assert "我记得" in result
        assert "important" in result

    def test_query_memory_no_results(self, brain):
        memory = MockMemory(results=[])
        brain.memory = memory
        tool = brain.tools["query_memory"]
        result = tool(keyword="nothing")
        assert "没有相关记忆" in result

    def test_query_memory_no_memory(self, brain):
        brain.memory = None
        tool = brain.tools["query_memory"]
        result = tool()
        assert "未就绪" in result
