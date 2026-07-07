"""
Claude 导出采集器

解析 Claude.ai 导出 ZIP/JSON，提取沟通风格、技术偏好、活跃时段。
与 ChatGPT 共享分析方法（_extract_messages 等），仅 ZIP 解析逻辑不同。
"""

import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alpha_id.collectors.base import CollectorInfo
from alpha_id.collectors.chatgpt import ChatGPTCollector
from alpha_id.profile_schema import AlphaIDProfile

logger = logging.getLogger(__name__)


class ClaudeCollector(ChatGPTCollector):
    """从 Claude 导出文件提取用户画像"""

    info = CollectorInfo(
        name="claude",
        display_name="Claude 导出文件",
        description="从 Claude 对话导出 ZIP/JSON 中提取沟通风格和技术偏好",
        category="ai_tool",
        priority=20,
        requires_input=True,
    )

    def detect(self) -> bool:
        for p in [Path.home() / "Downloads", Path.home() / "Desktop"]:
            for f in p.glob("*claude*"):
                if f.suffix in (".zip", ".json"):
                    return True
        return False

    def collect(self, input_path: Optional[Path] = None) -> Optional[AlphaIDProfile]:
        zip_path = input_path
        if zip_path is None:
            return None
        if not zip_path.exists():
            logger.error("文件不存在: %s", zip_path)
            return None

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                conv_file = None
                for candidate in ["conversations.json", "data.json", "claude_data.json"]:
                    if candidate in names:
                        conv_file = candidate
                        break
                if conv_file is None:
                    logger.error("ZIP 中未找到对话数据文件")
                    return None
                with zf.open(conv_file) as f:
                    data = json.load(f)
        except Exception as e:
            logger.error("ZIP 解析失败: %s", e)
            return None

        if isinstance(data, dict):
            conversations = data.get("conversations") or data.get("chat_messages") or []
        elif isinstance(data, list):
            conversations = data
        else:
            conversations = []

        if not isinstance(conversations, list) or len(conversations) < 3:
            logger.warning("对话数不足 3 条")
            return None

        profile = AlphaIDProfile(created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

        msgs, timestamps = self._extract_messages_claude(conversations)
        if not msgs:
            logger.warning("未找到用户消息")
            return None

        self._extract_communication(profile, msgs)
        self._extract_temporal(profile, timestamps)
        self._extract_technical(profile, msgs)

        return profile

    def summary(self, profile: AlphaIDProfile) -> str:
        lines = [
            "[Claude] 对话数据采集",
            f"   沟通风格: {profile.persona.communication.tone or '未知'}",
            f"   句子长度: {profile.persona.communication.sentence_length or '未知'}",
        ]
        if profile.persona.communication.active_hours:
            lines.append(
                f"   活跃时段: {', '.join(f'{h:02d}:00' for h in profile.persona.communication.active_hours[:5])}"
            )
        if profile.persona.technical.primary_languages:
            lines.append(f"   技术语言: {', '.join(profile.persona.technical.primary_languages)}")
        if profile.persona.technical.coding_style:
            lines.append(f"   编码风格: {profile.persona.technical.coding_style}")
        if profile.persona.temporal.work_rhythm:
            lines.append(f"   工作节奏: {profile.persona.temporal.work_rhythm}")
        return "\n".join(lines)

    def _extract_messages_claude(self, conversations: list) -> tuple[list[str], list[str]]:
        """Claude 特有的消息提取（字段名与 ChatGPT 不同）"""
        msgs = []
        timestamps = []
        for conv in conversations[:200]:
            ts = conv.get("create_time") or conv.get("created_at") or conv.get("updated_at")
            if ts:
                timestamps.append(str(ts))
            messages = conv.get("conversation") or conv.get("messages") or conv.get("chat_messages") or []
            for msg in messages:
                role = (msg.get("role") or msg.get("sender") or "").lower()
                if role not in ("user", "human"):
                    continue
                content = msg.get("content") or msg.get("text") or ""
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            msgs.append(part.get("text", ""))
                elif isinstance(content, str) and content.strip():
                    msgs.append(content)
        return msgs, timestamps


_instance = ClaudeCollector()
info, detect, collect, summary = _instance.create_module_functions()
