"""Mining extractor — 从扫描到的痕迹中抽取原始画像信号。"""

import json
import logging
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class ExtractedSignals:
    """单次抽取结果"""

    source_kind: str
    source_path: str
    messages: List[str] = field(default_factory=list)
    timestamps: List[str] = field(default_factory=list)
    code_extensions: List[str] = field(default_factory=list)
    bookmarks: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


def extract_from_path(root: str) -> List[ExtractedSignals]:
    """从指定路径抽取可推断画像的信号。"""

    scan_root = Path(root)
    results: List[ExtractedSignals] = []

    _extract_chat_exports(scan_root, results)
    _extract_git_signals(scan_root, results)
    _extract_code_signals(scan_root, results)
    _extract_browser_artifacts(scan_root, results)

    logger.info("extract_from_path complete: %s signals from %s", len(results), scan_root)
    return results


def _append(result: ExtractedSignals, **kwargs: Any) -> None:
    for key, value in kwargs.items():
        target = getattr(result, key)
        if isinstance(target, list):
            target.extend(value)


def _extract_chat_exports(scan_root: Path, results: List[ExtractedSignals]) -> None:
    for match in scan_root.rglob("*"):
        if not match.is_file() or match.suffix.lower() not in {".zip", ".json"}:
            continue
        name = match.name.lower()
        if "chatgpt" not in name and "claude" not in name:
            continue
        kind = "chatgpt_export" if "chatgpt" in name else "claude_export"
        result = ExtractedSignals(source_kind=kind, source_path=str(match))

        try:
            if match.suffix.lower() == ".zip":
                with zipfile.ZipFile(match, "r") as zf:
                    if kind == "chatgpt_export" and "conversations.json" in zf.namelist():
                        with zf.open("conversations.json") as f:
                            data = json.load(f)
                            msgs, timestamps = _extract_user_messages_from_conversations(data)
                            _append(result, messages=msgs, timestamps=timestamps, raw={"conversation_count": len(data)})
                    elif kind == "claude_export" and "conversations.json" in zf.namelist():
                        with zf.open("conversations.json") as f:
                            data = json.load(f)
                            msgs, timestamps = _extract_claude_messages(data)
                            _append(result, messages=msgs, timestamps=timestamps, raw={"conversation_count": len(data)})
            else:
                try:
                    with open(match, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    msgs, timestamps = _extract_user_messages_from_conversations(data)
                    _append(result, messages=msgs, timestamps=timestamps, raw={"conversation_count": len(data)})
                except Exception as e:
                    logger.debug("json extract failed: %s %s", match, e)
        except Exception as e:
            logger.debug("chat export extract failed: %s %s", match, e)

        if result.messages or result.timestamps:
            results.append(result)

    _scrub_extracted_signals(results)


def _extract_user_messages_from_conversations(conversations: List[Dict[str, Any]]) -> tuple[List[str], List[str]]:
    msgs: List[str] = []
    timestamps: List[str] = []
    for conv in conversations[:200]:
        ts = conv.get("create_time") or conv.get("createTime") or conv.get("timestamp")
        if ts:
            timestamps.append(str(ts))
        for msg in conv.get("messages") or conv.get("mapping", {}).values():
            role = ""
            content = ""
            if isinstance(msg, dict):
                role = msg.get("role", "") or msg.get("author", {}).get("role", "")
                content = msg.get("content", "") or ""
            if role != "user":
                continue
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("content_type") == "text":
                        text = part.get("text", "" or "")
                        if text and text.strip():
                            msgs.append(text.strip())
            elif isinstance(content, str) and content.strip():
                msgs.append(content.strip())
    return msgs, timestamps


def _scrub_extracted_signals(results: List[ExtractedSignals]) -> None:
    secrets_pattern = re.compile(
        r"(?i)(sk|api|token|secret|password|passwd|private_key|access_key)\s*[:=]\s*[^\s,;，。；\n]{6,}"
    )
    for result in results:
        result.messages = [_scrub_text(text, secrets_pattern) for text in result.messages]
        result.bookmarks = [_scrub_text(text, secrets_pattern) for text in result.bookmarks]


def _scrub_text(text: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(text, str):
        return text
    return re.sub(pattern, "[REDACTED]", text)


def _extract_claude_messages(conversations: List[Dict[str, Any]]) -> tuple[List[str], List[str]]:
    msgs: List[str] = []
    timestamps: List[str] = []
    for conv in conversations[:200]:
        ts = conv.get("created_at") or conv.get("updated_at") or conv.get("createdAt")
        if ts:
            timestamps.append(str(ts))
        for msg in conv.get("chat_messages") or conv.get("messages") or []:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "") or msg.get("sender", "")
            if role != "user":
                continue
            content = msg.get("text") or msg.get("content") or ""
            if isinstance(content, str) and content.strip():
                msgs.append(content.strip())
    return msgs, timestamps


def _extract_git_signals(scan_root: Path, results: List[ExtractedSignals]) -> None:
    for git_dir in scan_root.rglob(".git"):
        if not git_dir.is_dir():
            continue
        repo = git_dir.parent
        result = ExtractedSignals(source_kind="git_repo", source_path=str(repo))
        exts = []
        for match in repo.rglob("*"):
            if match.is_file() and not match.name.startswith("."):
                exts.append(match.suffix.lower())
        if exts:
            result.code_extensions.extend(exts)
        results.append(result)


def _extract_code_signals(scan_root: Path, results: List[ExtractedSignals]) -> None:
    exts: List[str] = []
    for match in scan_root.rglob("*"):
        if match.is_file() and not match.name.startswith("."):
            exts.append(match.suffix.lower())
    if not exts:
        return
    top = [ext for ext, _ in Counter(exts).most_common(12) if ext]
    result = ExtractedSignals(source_kind="code_signals", source_path=str(scan_root), code_extensions=top)
    results.append(result)


def _extract_browser_artifacts(scan_root: Path, results: List[ExtractedSignals]) -> None:
    for match in scan_root.rglob("*"):
        if not match.is_file() or match.suffix.lower() not in {".html", ".json", ".csv"}:
            continue
        name = match.name.lower()
        if "bookmark" not in name and "history" not in name:
            continue
        result = ExtractedSignals(source_kind="browser_artifact", source_path=str(match))
        try:
            text = match.read_text(encoding="utf-8", errors="ignore")
            urls = re.findall(r"https?://[^\s\"'<>]+", text)
            result.bookmarks.extend(urls[:200])
        except Exception as e:
            logger.debug("browser artifact extract failed: %s %s", match, e)
        if result.bookmarks:
            results.append(result)
