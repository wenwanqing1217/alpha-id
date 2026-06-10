"""
AgentLoop 纯循环单元测试
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from core.agent import Tool, AgentLoop, _parse_tool_call, _make_tools


class TestTool:
    """Tool 数据模型测试"""

    def test_tool_basic(self):
        fn = lambda: "ok"
        t = Tool(name="test", description="测试工具", parameters={}, fn=fn)
        assert t.name == "test"
        assert t.description == "测试工具"
        assert t.parameters == {}

    def test_tool_to_schema(self):
        fn = lambda x: str(x)
        t = Tool(
            name="echo",
            description="回声",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "string"}},
            },
            fn=fn,
        )
        schema = t.to_schema()
        assert schema["name"] == "echo"
        assert schema["description"] == "回声"
        assert "properties" in schema["parameters"]

    def test_tool_call(self):
        t = Tool(
            name="add",
            description="加法",
            parameters={
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            },
            fn=lambda a, b: str(int(a) + int(b)),
        )
        result = t(a=1, b=2)
        assert result == "3"

    def test_tool_call_error_returns_message(self):
        t = Tool(name="crash", description="会崩溃", parameters={}, fn=lambda: 1 / 0)
        result = t()
        assert "[工具错误]" in result


class TestMakeTools:
    """_make_tools 集成测试"""

    def test_make_tools_returns_list(self):
        tools = _make_tools("Alpha-Test-001")
        assert len(tools) >= 12  # 基础 + 社交 + 记忆 + 行动
        names = [t.name for t in tools]
        assert "get_profile" in names
        assert "get_friends" in names
        assert "get_risk_score" in names
        assert "save_memory" in names
        assert "query_memory" in names
        assert "send_message" in names
        assert "send_friend_request" in names
        assert "plan_action" in names
        assert "execute_action" in names
        assert "list_pending_actions" in names
        assert "get_action_history" in names

    def test_tool_names_unique(self):
        tools = _make_tools("Alpha-Test-002")
        names = [t.name for t in tools]
        assert len(names) == len(set(names))

    def test_plan_action_tool_schema(self):
        """plan_action 工具的 JSON Schema 完整"""
        tools = _make_tools("Alpha-Test-003")
        plan = next(t for t in tools if t.name == "plan_action")
        schema = plan.to_schema()
        assert schema["name"] == "plan_action"
        assert "action_type" in schema["parameters"]["properties"]
        assert "platform" in schema["parameters"]["properties"]
        assert "intent" in schema["parameters"]["properties"]
        assert "required" in schema["parameters"]
        assert "action_type" in schema["parameters"]["required"]

    def test_prepare_tools_json(self):
        """工具 schema 能正确序列化为 JSON（供 LLM 使用）"""
        tools = _make_tools("Alpha-Test-004")
        # 所有工具都应支持 to_schema → JSON 序列化
        schemas = [t.to_schema() for t in tools]
        json_str = json.dumps(schemas, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        names_in_json = [t["name"] for t in parsed]
        assert "plan_action" in names_in_json
        assert "execute_action" in names_in_json
        assert len(parsed) >= 12


class TestParseToolCall:
    """__TOOL_CALL__ 标记解析测试"""

    def test_parse_basic(self):
        text = "__TOOL_CALL__ get_profile({})"
        result = _parse_tool_call(text)
        assert result is not None
        _, name, args = result
        assert name == "get_profile"
        assert args == {}

    def test_parse_with_args(self):
        text = '__TOOL_CALL__ send_message({"to_alpha_id": "Alpha-002", "content": "你好"})'
        result = _parse_tool_call(text)
        assert result is not None
        _, name, args = result
        assert name == "send_message"
        assert args["to_alpha_id"] == "Alpha-002"
        assert args["content"] == "你好"

    def test_parse_no_tool_call(self):
        text = "这是普通文本，不是工具调用"
        result = _parse_tool_call(text)
        assert result is None

    def test_parse_multiple_lines(self):
        text = "先查一下\n__TOOL_CALL__ get_profile({})\n然后再看看"
        result = _parse_tool_call(text)
        assert result is not None
        assert result[0] == "" or result[1] == "get_profile"

    def test_parse_empty_args(self):
        text = "__TOOL_CALL__ get_profile()"
        result = _parse_tool_call(text)
        assert result is not None
        _, name, args = result
        assert name == "get_profile"
        assert args == {}

    def test_parse_malformed_json(self):
        text = '__TOOL_CALL__ send_message({"to": "abc"})'
        result = _parse_tool_call(text)
        assert result is not None
        _, name, args = result
        assert name == "send_message"
        # 如果 JSON 解析失败，args 为空字典
        assert isinstance(args, dict)

    def test_parse_tool_call_in_middle_of_text(self):
        text = "让我帮你查一下\n__TOOL_CALL__ get_risk_score({})\n结果如下"
        result = _parse_tool_call(text)
        assert result is not None
        assert result[1] == "get_risk_score"


class TestAgentLoop:
    """AgentLoop 核心循环测试"""

    def test_init(self):
        loop = AgentLoop("Alpha-Loop-001")
        assert loop.alpha_id == "Alpha-Loop-001"
        assert loop.model == "deepseek-v4-flash"
        assert loop.max_turns == 3
        assert len(loop.tools) > 0
        assert loop.history == []

    def test_custom_model(self):
        loop = AgentLoop("Alpha-Loop-002", model="deepseek-chat", max_turns=5)
        assert loop.model == "deepseek-chat"
        assert loop.max_turns == 5

    @patch("core.agent._call_llm")
    def test_run_direct_reply(self, mock_llm):
        """LLM 直接回复（不调用工具）"""
        mock_llm.return_value = "你的身份信息已经查到了，一切正常。"
        loop = AgentLoop("Alpha-Loop-003")
        reply = loop.run("帮我查身份")
        assert reply == "你的身份信息已经查到了，一切正常。"
        assert len(loop.history) == 2  # user + assistant

    @patch("core.agent._call_llm")
    def test_run_tool_call_sequence(self, mock_llm):
        """LLM 调用一次工具后回复"""
        # 第一次返回工具调用，第二次返回最终回答
        mock_llm.side_effect = [
            "__TOOL_CALL__ get_profile({})",
            "以下是你的身份信息：...",
        ]
        loop = AgentLoop("Alpha-Loop-004")
        # patch container.identity.get_user_profile 返回模拟数据
        from alpha_id.container import Container

        orig = Container.instance().identity
        Container.instance()._identity = MagicMock()
        Container.instance()._identity.get_user_profile.return_value = {
            "alpha_id": "Alpha-Loop-004",
            "nickname": "测试",
        }
        try:
            reply = loop.run("我是谁")
            assert reply == "以下是你的身份信息：..."
            assert len(loop.history) == 2
        finally:
            Container.instance()._identity = orig

    @patch("core.agent._call_llm")
    def test_max_turns_reached(self, mock_llm):
        """达到最大轮次后返回超时信息"""
        mock_llm.return_value = "__TOOL_CALL__ get_profile({})"
        loop = AgentLoop("Alpha-Loop-005", max_turns=3)
        from alpha_id.container import Container

        orig = Container.instance().identity
        Container.instance()._identity = MagicMock()
        Container.instance()._identity.get_user_profile.return_value = {"alpha_id": "Alpha-Loop-005"}
        try:
            reply = loop.run("循环测试")
            assert "达到最大轮次" in reply
        finally:
            Container.instance()._identity = orig

    @patch("core.agent._call_llm")
    def test_unknown_tool_returns_error(self, mock_llm):
        """LLM 调用不存在的工具"""
        mock_llm.side_effect = [
            "__TOOL_CALL__ nonexistent_tool({})",
            "好的我知道了",
        ]
        loop = AgentLoop("Alpha-Loop-006")
        from alpha_id.container import Container

        orig_id = Container.instance().identity
        Container.instance()._identity = MagicMock()
        try:
            reply = loop.run("调用不存在的工具")
            assert reply == "好的我知道了"
        finally:
            Container.instance()._identity = orig_id


class TestCallLLM:
    """_call_llm 边界情况测试"""

    def test_no_api_key(self):
        """没有 API key 时返回提示信息"""
        import os

        old_key = os.environ.pop("OPENAI_API_KEY", None)
        old_key2 = os.environ.pop("COZE_WORKLOAD_IDENTITY_API_KEY", None)
        try:
            from core.agent import _call_llm

            result = _call_llm([{"role": "user", "content": "hi"}], [])
            assert "未配置" in result
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key
            if old_key2:
                os.environ["COZE_WORKLOAD_IDENTITY_API_KEY"] = old_key2


def test_parse_tool_call_function():
    """_parse_tool_call 作为模块级函数的测试"""
    from core.agent import _parse_tool_call

    result = _parse_tool_call("__TOOL_CALL__ test({})")
    assert result is not None
    assert result[1] == "test"


class TestAgentSkillIntegration:
    """AgentLoop × Skill × Attribution 集成测试"""

    def test_skill_tools_are_registered(self):
        """AgentLoop 包含技能相关工具"""
        tools = _make_tools("Alpha-Skill-001")
        names = [t.name for t in tools]
        assert "list_skills" in names
        assert "execute_skill" in names
        assert "get_skill_info" in names

    def test_skill_tools_unique(self):
        """技能工具名称不冲突"""
        tools = _make_tools("Alpha-Skill-002")
        names = [t.name for t in tools]
        assert len(names) == len(set(names))

    def test_execute_skill_pass_executor_did(self, tmp_path):
        """execute_skill 传递 executor_did 实现归因"""
        from alpha_id.skill_signer import (
            SkillRegistry,
            SkillAttributionTracker,
            SkillRuntime,
            sign_skill,
            SkillPackage,
        )
        from alpha_id.signer import AIDSigner

        # 注入隔离的环境变量来改变 home 目录路径
        import os

        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(tmp_path / "home")

        try:
            author = AIDSigner()
            author.generate()
            skill_file = tmp_path / "greet.py"
            skill_file.write_text('def main(p): return "hello " + p.get("name","world")')
            pkg = sign_skill(skill_file, author, name="greet")

            # 直接使用注册表注册
            storage = str(tmp_path / "skills")
            tracker_dir = str(tmp_path / "attribs")
            reg = SkillRegistry(storage_dir=storage)
            tracker = SkillAttributionTracker(storage_dir=tracker_dir)
            rt = SkillRuntime(reg, tracker=tracker)
            with open(skill_file, "rb") as fh:
                reg.register(pkg, content=fh.read())

            # 模拟 _make_tools 中的 execute_skill 行为
            agent_did = "did:aid:agent-001"
            result = rt.execute("greet", '{"name":"Agent"}', executor_did=agent_did)
            assert "hello Agent" in result

            stats = tracker.get_author_stats(author.did)
            assert stats["total_executions"] == 1
            assert stats["unique_executors"] >= 1
        finally:
            if old_home is not None:
                os.environ["HOME"] = old_home
            else:
                del os.environ["HOME"]
