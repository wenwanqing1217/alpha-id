"""DIY CLI 测试：本地意图解析、LLM 解析回退、执行器路由"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from alpha_id import diy_cli


class TestLocalIntentParse:
    def test_scaffold_init_detected(self):
        it = diy_cli._local_parse_intent("帮我搭一个 Python 项目脚手架在 /tmp/demo")
        assert it.intent == "scaffold.init"

    def test_workflow_execute_detected(self):
        it = diy_cli._local_parse_intent("帮我执行一个渠道运营工作流模板")
        assert it.intent == "workflow.execute"

    def test_feishu_sync_detected(self):
        it = diy_cli._local_parse_intent("同步飞书通讯录，自动加平台好友")
        assert it.intent == "feishu.sync_contacts"

    def test_a2a_register_and_price_param(self):
        it = diy_cli._local_parse_intent("接一个翻译 agent，价格 2 积分一次")
        assert it.intent == "a2a.register"
        assert it.params.get("price_credits") == 2

    def test_unknown_falls_back_to_brain_chat(self):
        it = diy_cli._local_parse_intent("今天天气怎么样")
        assert it.intent == "brain.chat"


class TestBusinessIntentParse:
    """业务场景意图（闲鱼/小红书/抖音/短剧/视频/游戏/文案）"""

    def test_channel_copy_xianyu(self):
        it = diy_cli._local_parse_intent("生成一个咸鱼文案 商品=北欧风香薰 卖点=大豆蜡 价格=59 成色=全新")
        assert it.intent == "channel_copy.generate"
        assert it.params.get("product") == "北欧风香薰"
        assert it.params.get("price") == "59"

    def test_channel_copy_xiaohongshu(self):
        it = diy_cli._local_parse_intent("写一篇小红书种草文案 商品=香薰蜡烛")
        assert it.intent == "channel_copy.generate"

    def test_video_generate(self):
        it = diy_cli._local_parse_intent("生成一个短视频 主题=北欧风香薰蜡烛种草")
        assert it.intent == "video.generate"
        assert it.params.get("subject") == "北欧风香薰蜡烛种草"

    def test_douyin_publish(self):
        it = diy_cli._local_parse_intent("发抖音 标题=我的短剧 内容=剧情简介")
        assert it.intent == "douyin.publish"
        assert it.params.get("title") == "我的短剧"

    def test_shortdramas_submit(self):
        it = diy_cli._local_parse_intent("投一个短剧预审 标题=重生之我在平台卖香薰")
        assert it.intent == "shortdramas.submit"

    def test_game_generate(self):
        it = diy_cli._local_parse_intent("做个太空射击小游戏")
        assert it.intent == "game.generate"

    def test_codex_delegate(self):
        it = diy_cli._local_parse_intent("帮我写个爬虫抓豆瓣电影")
        assert it.intent == "codex.delegate"


class TestLLMParseFallback:
    def test_llm_failure_falls_back_to_local(self):
        """LLM 调用抛异常时必须回退到本地解析，而不是崩掉"""
        with patch("httpx.post", side_effect=RuntimeError("llm down")):
            it = diy_cli._llm_parse_intent("生成一个小红书文案 商品=香薰")
        assert it.intent == "channel_copy.generate"

    def test_llm_json_parsed(self):
        fake_resp = MagicMock()
        fake_resp.json.return_value = {
            "choices": [{"message": {"content": '{"intent": "a2a.call", "params": {"skill": "ping"}, "confidence": 0.9}'}}]
        }
        with patch("httpx.post", return_value=fake_resp):
            with patch("core.settings.settings.llm_api_key", "test-key"):
                with patch("core.settings.settings.llm_base_url", "http://llm.local/v1"):
                    it = diy_cli._llm_parse_intent("调用 ping skill")
        assert it.intent == "a2a.call"
        assert it.params.get("skill") == "ping"
        assert it.confidence == 0.9


class TestIntentExecutor:
    def test_execute_routes_to_handler(self):
        ex = diy_cli.IntentExecutor(alpha_id="Alpha-T")
        result = ex.execute(diy_cli.ParsedIntent("brain.chat", {}, 0.9))
        assert result is not None
        assert isinstance(result, dict)

    def test_unknown_intent_routes_to_brain_chat(self):
        ex = diy_cli.IntentExecutor(alpha_id="Alpha-T")
        result = ex.execute(diy_cli.ParsedIntent("not.a.real.intent", {}, 0.1))
        assert isinstance(result, dict)

    def test_diy_chat_runs_executor(self):
        """diy_chat 端到端：本地解析 → 执行器（Typer 命令打印结果，不抛异常）"""
        with patch.object(
            diy_cli, "IntentExecutor",
            return_value=MagicMock(execute=MagicMock(return_value={"action": "ok"})),
        ) as exec_cls:
            diy_cli.diy_chat("随便聊聊", use_local_parser=True, dry_run=False)
        exec_cls.return_value.execute.assert_called_once()
