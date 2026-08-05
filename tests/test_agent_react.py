# -*- coding: utf-8 -*-
"""ReActEngine unit tests"""

import json
from unittest.mock import MagicMock, patch


class TestReActEngineInit:
    def test_import(self):
        from core.agent_react import ReActEngine

        assert ReActEngine is not None

    def test_init_without_api_key(self):
        from core.agent_react import ReActEngine
        from core.settings import settings

        # settings.llm_api_key 在导入时已加载，需要 patch 为空
        with patch.object(settings, "llm_api_key", ""):
            engine = ReActEngine(alpha_id="Alpha-Test-001")
        assert engine.alpha_id == "Alpha-Test-001"
        assert engine.api_key == ""
        assert len(engine.tools) == 6

    def test_init_with_brain(self):
        from core.agent_react import ReActEngine

        brain = MagicMock()
        engine = ReActEngine(alpha_id="Alpha-Test-001", brain=brain)
        assert engine.brain is brain

    def test_tool_registry_has_expected_tools(self):
        from core.agent_react import ReActEngine

        engine = ReActEngine(alpha_id="Alpha-Test-001")
        tool_names = {t.name for t in engine.tools}
        expected = {"search_memory", "query_profile", "get_time", "evaluate_risk", "get_status", "save_insight"}
        assert tool_names == expected


class TestThinkNoApiKey:
    def test_think_returns_error_without_key(self):
        from core.agent_react import ReActEngine
        from core.settings import settings

        # settings.llm_api_key 在导入时已加载，需要 patch 为空
        with patch.object(settings, "llm_api_key", ""):
            engine = ReActEngine(alpha_id="Alpha-Test-001")
        result = engine.think()
        assert result["status"] == "error"
        assert "LLM" in result["observation"]


class TestThinkWithMockLLM:
    @patch("core.agent_react._call_llm")
    def test_think_final_answer(self, mock_call_llm):
        from core.agent_react import ReActEngine

        mock_call_llm.return_value = "\u601d\u8003\uff1a\u72b6\u6001\u6b63\u5e38\uff0c\u65e0\u9700\u884c\u52a8\u3002\n\u6700\u7ec8\uff1a\u5f53\u524d\u72b6\u6001\u826f\u597d\u3002"
        engine = ReActEngine(alpha_id="Alpha-Test-001", llm_api_key="sk-mock")
        result = engine.think()
        assert result["status"] == "ok"
        assert result["action"] == "final_answer"
        assert result["tool_calls"] == 0

    @patch("core.agent_react._call_llm")
    def test_think_one_tool_call(self, mock_call_llm):
        from core.agent_react import ReActEngine

        mock_call_llm.side_effect = [
            "\u601d\u8003\uff1a\u6211\u9700\u8981\u67e5\u770b\u5f53\u524d\u72b6\u6001\u3002\n__TOOL_CALL__ get_status({})",
            "\u601d\u8003\uff1a\u72b6\u6001\u6b63\u5e38\uff0c\u65e0\u9700\u64cd\u4f5c\u3002\n\u6700\u7ec8\uff1a\u5f53\u524d\u72b6\u6001\u826f\u597d\u3002",
        ]
        engine = ReActEngine(alpha_id="Alpha-Test-001", llm_api_key="sk-mock")
        result = engine.think()
        assert result["status"] == "ok"
        assert result["tool_calls"] == 1

    @patch("core.agent_react._call_llm")
    def test_think_max_turns(self, mock_call_llm):
        from core.agent_react import ReActEngine

        mock_call_llm.return_value = "\u601d\u8003\uff1a\u7ee7\u7eed\u5206\u6790\u3002\n__TOOL_CALL__ get_time({})"
        engine = ReActEngine(alpha_id="Alpha-Test-001", llm_api_key="sk-mock")
        engine.max_turns = 2
        result = engine.think()
        assert result["status"] == "ok"
        assert result["action"] == "max_turns_reached"
        assert result["tool_calls"] == 2

    @patch("core.agent_react._call_llm")
    def test_think_unknown_tool(self, mock_call_llm):
        from core.agent_react import ReActEngine

        mock_call_llm.return_value = (
            "\u601d\u8003\uff1a\u8bd5\u8bd5\u672a\u77e5\u5de5\u5177\u3002\n__TOOL_CALL__ fake_tool({})"
        )
        engine = ReActEngine(alpha_id="Alpha-Test-001", llm_api_key="sk-mock")
        result = engine.think()
        assert result["status"] == "ok"


class TestToolFunctions:
    def test_get_time_tool_exists(self):
        from core.agent_react import ReActEngine

        engine = ReActEngine(alpha_id="Alpha-Test-001")
        tool = {t.name: t for t in engine.tools}["get_time"]
        result = tool()
        assert len(result) > 0

    def test_search_memory_without_brain(self):
        from core.agent_react import ReActEngine

        engine = ReActEngine(alpha_id="Alpha-Test-001")
        result = engine._search_memory("test")
        assert "\u672a\u5c31\u7eea" in result

    def test_evaluate_risk(self):
        from core.agent_react import ReActEngine

        engine = ReActEngine(alpha_id="Alpha-Test-001")
        result = engine._evaluate_risk("\u67e5\u770b\u72b6\u6001")
        data = json.loads(result)
        assert "risk_score" in data
        assert "risk_level" in data

    def test_evaluate_risk_high(self):
        from core.agent_react import ReActEngine

        engine = ReActEngine(alpha_id="Alpha-Test-001")
        result = engine._evaluate_risk("\u5220\u9664\u5e76\u4fee\u6539\u6240\u6709\u6570\u636e")
        data = json.loads(result)
        assert data["risk_level"] == "high"

    def test_save_insight_without_brain(self):
        from core.agent_react import ReActEngine

        engine = ReActEngine(alpha_id="Alpha-Test-001")
        result = engine._save_insight("test insight")
        assert "\u672a\u5c31\u7eea" in result


class TestTwinBrainIntegration:
    def test_brain_has_react_property(self):
        from core.twin_brain import TwinBrain

        brain = TwinBrain(alpha_id="Alpha-React-001")
        assert hasattr(brain, "react")

    def test_brain_settings_has_use_react(self):
        from core.twin_brain import BrainSettings

        settings = BrainSettings()
        assert settings.use_react is True

    def test_think_includes_react_result(self):
        from core.twin_brain import BrainSettings, TwinBrain

        settings = BrainSettings(use_agent_chat=True, use_react=True)
        brain = TwinBrain(alpha_id="Alpha-React-002", settings=settings)
        brain.awake()
        brain.idle()
        mock_result = {
            "status": "ok",
            "thought": "check done",
            "action": "final_answer",
            "observation": "",
            "tool_calls": 0,
        }
        brain._react = MagicMock()
        brain._react.think.return_value = mock_result
        result = brain.think()
        assert result["agent_thought"] == "check done"
        assert result["react_result"] == mock_result
