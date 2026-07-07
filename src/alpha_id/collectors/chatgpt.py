"""
ChatGPT 导出采集器

解析 ChatGPT 导出 ZIP/JSON，提取沟通风格、技术偏好、活跃时段。
"""

import json
import logging
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alpha_id.collectors.base import BaseCollector, CollectorInfo
from alpha_id.profile_schema import AlphaIDProfile

logger = logging.getLogger(__name__)


class ChatGPTCollector(BaseCollector):
    """从 ChatGPT 导出文件提取用户画像"""

    info = CollectorInfo(
        name="chatgpt",
        display_name="ChatGPT 导出文件",
        description="从 ChatGPT 数据导出 ZIP/JSON 中提取对话风格、技术偏好、活跃时段",
        category="ai_tool",
        priority=10,
        requires_input=True,
    )

    def detect(self) -> bool:
        """检测是否存在 ChatGPT 导出数据"""
        for p in [Path.home() / "Downloads", Path.home() / "Desktop"]:
            for f in p.glob("*chatgpt*"):
                if f.suffix in (".zip", ".json"):
                    return True
        return False

    def collect(self, input_path: Optional[Path] = None) -> Optional[AlphaIDProfile]:
        """解析 ChatGPT 导出 ZIP/JSON → 返回 profile"""
        zip_path = input_path
        if zip_path is None:
            return None
        if not zip_path.exists():
            logger.error("文件不存在: %s", zip_path)
            return None

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                if "conversations.json" not in zf.namelist():
                    logger.error("ZIP 中未找到 conversations.json")
                    return None
                with zf.open("conversations.json") as f:
                    conversations = json.load(f)
        except Exception as e:
            logger.error("ZIP 解析失败: %s", e)
            return None

        if not isinstance(conversations, list) or len(conversations) < 3:
            logger.warning("对话数不足 3 条")
            return None

        profile = AlphaIDProfile(created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

        msgs, timestamps = self._extract_messages(conversations)
        if not msgs:
            logger.warning("未找到用户消息")
            return None

        self._extract_communication(profile, msgs)
        self._extract_temporal(profile, timestamps)
        self._extract_technical(profile, msgs)

        return profile

    def summary(self, profile: AlphaIDProfile) -> str:
        """采集摘要"""
        lines = [
            "[ChatGPT] 对话数据采集",
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

    # ─── 内部分析方法（可被子类复用） ───

    def _extract_messages(self, conversations: list) -> tuple[list[str], list[str]]:
        """从对话列表提取用户消息和时间戳"""
        msgs = []
        timestamps = []
        for conv in conversations[:200]:
            ts = conv.get("create_time")
            if ts:
                timestamps.append(str(ts))
            for msg in conv.get("messages") or []:
                role = msg.get("role", "") or msg.get("author", {}).get("role", "")
                if role != "user":
                    continue
                content = msg.get("content", "") or ""
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("content_type") == "text":
                            msgs.append(part.get("text", ""))
                elif isinstance(content, str) and content.strip():
                    msgs.append(content)
        return msgs, timestamps

    def _extract_communication(self, profile: AlphaIDProfile, msgs: list[str]):
        """提取沟通风格"""
        lengths = [len(m.split()) for m in msgs]
        avg = sum(lengths) / len(lengths)
        profile.persona.communication.sentence_length = "short" if avg < 15 else ("medium" if avg < 40 else "long")
        question_ratio = sum(m.count("?") for m in msgs) / max(len("".join(msgs)), 1)
        profile.persona.communication.tone = "analytical" if question_ratio > 0.05 else "direct"

    def _extract_temporal(self, profile: AlphaIDProfile, timestamps: list[str]):
        """提取活跃时段和工作节奏"""
        hour_counts: Counter[int] = Counter()
        for ts in timestamps:
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                hour_counts[dt.hour] += 1
            except (ValueError, TypeError):
                continue
        if hour_counts:
            profile.persona.communication.active_hours = sorted(h for h, _ in hour_counts.most_common(5))
            night = sum(c for h, c in hour_counts.items() if h >= 22 or h <= 5)
            day = sum(c for h, c in hour_counts.items() if 6 <= h <= 18)
            profile.persona.temporal.work_rhythm = (
                "night_owl" if (night + day > 0 and night / (night + day) > 0.4) else "daytime"
            )

    def _extract_technical(self, profile: AlphaIDProfile, msgs: list[str]):
        """提取技术偏好"""
        text = " ".join(msgs)
        langs = []
        for lang, pat in {
            "Python": r"\bpython\b",
            "TypeScript": r"\btypescript\b",
            "JavaScript": r"\bjavascript\b",
            "Rust": r"\brust\b",
            "Go": r"\bgo\b",
            "Java": r"\bjava\b",
        }.items():
            if re.search(pat, text, re.IGNORECASE):
                langs.append(lang)
        profile.persona.technical.primary_languages = langs[:5]

        if re.search(r"\b(functional|lambda|immutable)\b", text, re.IGNORECASE):
            profile.persona.technical.coding_style = "functional"
        elif re.search(r"\b(class|inheritance|interface)\b", text, re.IGNORECASE):
            profile.persona.technical.coding_style = "oop"
        else:
            profile.persona.technical.coding_style = "mixed"


# ─── 模块级兼容函数（profile_cli.py 的 getattr 调用依赖这些） ───

_instance = ChatGPTCollector()

info, detect, collect, summary = _instance.create_module_functions()
