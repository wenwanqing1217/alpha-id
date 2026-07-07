"""
Alpha-ID 用户故事测试 — P0 闭环

覆盖"真实用户使用流程"，不 Mock。
每次跑之前确保 ~/.alpha-id/ 可写。
"""

import json
import zipfile
from pathlib import Path

import pytest

from alpha_id.collectors.chatgpt import collect
from alpha_id.profile_schema import (
    ensure_profile_dir,
    load_profile,
    profile_exists,
    save_profile,
    summary,
)

# 构造一个最小 ChatGPT 导出 ZIP（3 条对话）
SAMPLE_CONVERSATIONS = [
    {
        "title": "讨论 MCP 协议",
        "create_time": "2026-06-02T14:30:00Z",
        "messages": [
            {"role": "user", "content": "你觉得 MCP 协议的未来怎么样？我想了解一下它的设计思路。"},
            {"role": "assistant", "content": "MCP 是 Anthropic 发起的开放协议，已经被 Linux 基金会接管。"},
        ],
    },
    {
        "title": "Python 异步编程",
        "create_time": "2026-06-01T22:00:00Z",
        "messages": [
            {"role": "user", "content": "asyncio 和 trio 有什么区别？我在写一个 Python FastAPI 应用。"},
            {"role": "assistant", "content": "asyncio 是标准库，trio 更简洁但生态较小。"},
        ],
    },
    {
        "title": "深夜代码审查",
        "create_time": "2026-06-01T01:30:00Z",
        "messages": [
            {"role": "user", "content": "帮我 review 这段 Rust 代码，用 functional 风格重构。"},
            {"role": "assistant", "content": "好的，我看到你用了很多 map 和 filter，风格不错。"},
        ],
    },
]


@pytest.fixture
def chatgpt_zip(tmp_path):
    """构造测试用 ChatGPT 导出 ZIP"""
    zip_path = tmp_path / "chatgpt_export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("conversations.json", json.dumps(SAMPLE_CONVERSATIONS))
    return zip_path


class TestUserStoryColdStart:
    """用户故事 1：冷启动流程"""

    def test_collect_creates_profile(self, chatgpt_zip):
        """aid collect chatgpt <zip> → profile 文件存在"""
        profile = collect(chatgpt_zip)
        assert profile is not None, "采集应返回 profile 对象"
        assert profile.persona is not None, "profile 应包含 persona"

        # 保存后验证
        save_profile(profile)
        assert profile_exists(), "profile 文件应存在于 ~/.alpha-id/"

    def test_collect_extracts_communication_style(self, chatgpt_zip):
        """采集后应提取出沟通风格"""
        profile = collect(chatgpt_zip)
        assert profile is not None
        assert profile.persona.communication.tone is not None, "应提取出语气"
        assert profile.persona.communication.sentence_length is not None, "应提取出句子长度"

    def test_collect_detects_tech_preferences(self, chatgpt_zip):
        """采集后应检测到用户技术偏好"""
        profile = collect(chatgpt_zip)
        assert profile is not None
        assert len(profile.persona.technical.primary_languages) > 0, "应检测到编程语言"
        assert "Python" in profile.persona.technical.primary_languages, "应检测到 Python"
        assert "Rust" in profile.persona.technical.primary_languages, "应检测到 Rust"

    def test_collect_detects_night_owl(self, chatgpt_zip):
        """采集后应识别活跃时段（凌晨有对话）"""
        profile = collect(chatgpt_zip)
        assert profile is not None
        active = profile.persona.communication.active_hours
        assert 1 in active or 2 in active, "应包含凌晨时段"

    def test_collect_invalid_zip_returns_none(self, tmp_path):
        """无效 ZIP 应返回 None 而不是崩溃"""
        bad = tmp_path / "not_a_zip.txt"
        bad.write_text("not a zip file")
        result = collect(bad)
        assert result is None, "无效文件应返回 None"

    def test_empty_collect_returns_none(self, tmp_path):
        """空 ZIP 应返回 None 而不是崩溃"""
        empty_zip = tmp_path / "empty.zip"
        with zipfile.ZipFile(empty_zip, "w") as zf:
            zf.writestr("conversations.json", "[]")
        result = collect(empty_zip)
        assert result is None, "空对话列表应返回 None"


class TestUserStoryMagicMoment:
    """用户故事 2：画像展示"""

    def test_profile_summary_contains_key_info(self, chatgpt_zip):
        """summary() 应包含关键画像信息"""
        profile = collect(chatgpt_zip)
        profile.did = "did:aid:test123"
        text = summary(profile)
        assert "Profile" in text, "摘要应包含 Profile 标题"
        assert "did:aid:test123" in text, "摘要应包含 DID"
        assert "Python" in text or "Rust" in text, "摘要应包含语言信息"
        assert "沟通风格" in text or "风格" in text, "摘要应包含沟通风格"

    def test_profile_json_format(self, chatgpt_zip):
        """to_dict() 应输出可用 JSON"""
        profile = collect(chatgpt_zip)
        assert profile is not None
        d = profile.to_dict()
        assert "profile_version" in d, "JSON 应包含版本号"
        assert "persona" in d, "JSON 应包含 persona"
        assert "communication" in d["persona"], "persona 应包含 communication"
        assert "technical" in d["persona"], "persona 应包含 technical"


class TestUserStorySaveLoad:
    """用户故事 3：profile 持久化"""

    def test_save_then_load(self, chatgpt_zip):
        """保存后再加载应保持数据一致"""
        profile = collect(chatgpt_zip)
        profile.did = "did:aid:persist_test"
        save_profile(profile)

        loaded = load_profile()
        assert loaded is not None, "应能加载 profile"
        assert loaded.did == "did:aid:persist_test", "加载后 DID 应一致"
        assert loaded.persona.communication.tone == profile.persona.communication.tone, "加载后沟通风格应一致"

    def test_profile_version_in_output(self, chatgpt_zip):
        """profile 应包含正确的版本号"""
        profile = collect(chatgpt_zip)
        assert profile.profile_version == "0.1.0", "版本号应为 0.1.0"
