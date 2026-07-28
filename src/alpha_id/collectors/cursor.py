"""
Cursor 导出采集器 — P1 版本

Cursor 是 AI 编程 IDE，数据存储在本地 SQLite 数据库中。
支持从 Cursor 的对话历史中提取用户编码偏好和技术栈信息。
"""

import json
import logging
import os
import re
import sqlite3
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alpha_id.profile_schema import AlphaIDProfile

logger = logging.getLogger(__name__)


def info():
    """采集器元信息 — 遵循 COLLECTOR_PROTOCOL v1.0"""
    return {
        "name": "cursor",
        "display_name": "Cursor IDE",
        "description": "从 Cursor 本地 SQLite 数据库或导出 ZIP 中提取编码风格和技术偏好",
        "category": "ide",
        "priority": 30,
        "requires_input": False,
    }


def detect() -> bool:
    """检测是否存在 Cursor 数据（本地 SQLite 或导出 ZIP）"""
    # 检查 Cursor 本地数据目录
    cursor_dirs = [
        Path.home() / "AppData" / "Roaming" / "Cursor",
        Path.home() / ".cursor",
    ]
    for d in cursor_dirs:
        if d.exists():
            return True
    # 检查导出文件
    for p in [Path.home() / "Downloads", Path.home() / "Desktop", Path.home() / ".alpha-id"]:
        for f in p.glob("*cursor*"):
            if f.suffix in (".zip", ".db", ".sqlite"):
                return True
    return False


def summary(profile: AlphaIDProfile) -> str:
    """采集摘要"""
    lines = [
        "[Cursor] 代码对话数据采集",
    ]
    if profile.persona.communication.tone:
        lines.append(f"   沟通风格: {profile.persona.communication.tone}")
    if profile.persona.technical.primary_languages:
        lines.append(f"   技术语言: {', '.join(profile.persona.technical.primary_languages)}")
    if profile.persona.technical.coding_style:
        lines.append(f"   编码风格: {profile.persona.technical.coding_style}")
    if profile.persona.temporal.work_rhythm:
        lines.append(f"   工作节奏: {profile.persona.temporal.work_rhythm}")
    return "\n".join(lines)


def _extract_from_sqlite(db_path: Path) -> Optional[list]:
    """从 Cursor 本地 SQLite 数据库提取对话"""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        # Cursor 使用多个可能的表名
        tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        _ALLOWED_TABLE_PREFIXES = ("cursor_", "chat_", "conversation_", "message_", "thread_")  # noqa: N806

        conversations = []
        for tbl in table_names:
            if not tbl.startswith(_ALLOWED_TABLE_PREFIXES):
                continue
            if any(k in tbl.lower() for k in ["conversation", "chat", "message", "thread"]):
                # 安全：验证表名只包含字母数字下划线，防止 SQL 注入
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", tbl):
                    logger.warning("跳过非法表名: %s", tbl)
                    continue
                try:
                    rows = cursor.execute(f'SELECT * FROM "{tbl}" LIMIT 200').fetchall()
                    col_names = [d[0] for d in cursor.description]
                    for row in rows:
                        conv = dict(zip(col_names, row))
                        conversations.append(conv)
                except Exception:
                    continue

        conn.close()
        return conversations if conversations else None
    except Exception as e:
        logger.debug("SQLite 解析失败: %s", e)
        return None


def collect(zip_path: Path) -> Optional[AlphaIDProfile]:
    """解析 Cursor 导出数据 → 返回 profile"""
    if not zip_path.exists():
        logger.error("文件不存在: %s", zip_path)
        return None

    msgs = []
    timestamps = []
    conversations = []

    # 尝试 ZIP 格式（用户手动导出的）
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".json"):
                    data = json.loads(zf.read(name))
                    if isinstance(data, list):
                        conversations.extend(data)
                    elif isinstance(data, dict):
                        conversations.append(data)
                elif name.endswith(".db") or "sqlite" in name:
                    # 安全：防止 Zip Slip 路径遍历攻击
                    # 验证解压路径在目标目录内
                    target_dir = (Path.home() / ".alpha-id" / "tmp").resolve()
                    tmp = (target_dir / name).resolve()
                    if not str(tmp).startswith(str(target_dir) + os.sep) and tmp != target_dir:
                        logger.warning("Zip Slip 攻击拦截: %s", name)
                        continue
                    tmp.parent.mkdir(parents=True, exist_ok=True)
                    tmp.write_bytes(zf.read(name))
                    rows = _extract_from_sqlite(tmp)
                    if rows:
                        conversations.extend(rows)
                    tmp.unlink(missing_ok=True)
    except zipfile.BadZipFile:
        # 尝试直接作为 SQLite 数据库文件读取
        rows = _extract_from_sqlite(zip_path)
        if rows:
            conversations = rows

    if len(conversations) < 3:
        logger.warning("对话数不足 3 条")
        return None

    profile = AlphaIDProfile(created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    # 提取用户消息
    for conv in conversations[:200]:
        if isinstance(conv, dict):
            ts = conv.get("timestamp") or conv.get("created_at") or conv.get("create_time")
            if ts:
                timestamps.append(str(ts))

            # 尝试多种字段名
            content = ""
            for key in ["text", "content", "message", "user_message", "input"]:
                val = conv.get(key, "")
                if isinstance(val, str) and val.strip():
                    content = val
                    break
                elif isinstance(val, list):
                    content = " ".join(str(v) for v in val if isinstance(v, str))
                    break

            if content.strip():
                msgs.append(content)

    if not msgs:
        logger.warning("未找到用户消息")
        return None

    # 沟通风格
    lengths = [len(m.split()) for m in msgs]
    avg = sum(lengths) / len(lengths)
    profile.persona.communication.sentence_length = "short" if avg < 15 else ("medium" if avg < 40 else "long")
    question_ratio = sum(m.count("?") for m in msgs) / max(len("".join(msgs)), 1)
    profile.persona.communication.tone = "analytical" if question_ratio > 0.05 else "direct"

    # 活跃时段
    hour_counts = Counter()
    for ts in timestamps:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            hour_counts[dt.hour] += 1
        except (ValueError, TypeError):
            continue
    if hour_counts:
        profile.persona.communication.active_hours = sorted(h for h, _ in hour_counts.most_common(5))

    # 技术偏好
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

    profile.persona.technical.coding_style = "mixed"
    if re.search(r"\b(functional|lambda|immutable)\b", text, re.IGNORECASE):
        profile.persona.technical.coding_style = "functional"
    elif re.search(r"\b(class|inheritance|interface)\b", text, re.IGNORECASE):
        profile.persona.technical.coding_style = "oop"

    return profile
