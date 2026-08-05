import pytest

pytestmark = pytest.mark.skip(reason="deleted module: alpha_id.mining")
"""Mining 模块回归测试"""

import json
from pathlib import Path

try:
    from alpha_id.mining import extract_from_path, scan_path
    from alpha_id.mining.inferrer import infer_profile
    from alpha_id.profile_schema import completeness
except ImportError:
    pass


def _write_chatgpt_export(tmp_path: Path) -> Path:
    conversations = [
        {
            "title": "Hello",
            "create_time": "2026-06-05T23:30:00Z",
            "messages": [{"role": "user", "content": "I love Python and Rust functional programming."}],
        }
    ]
    export_path = tmp_path / "chatgpt_export.json"
    export_path.write_text(json.dumps(conversations, ensure_ascii=False), encoding="utf-8")
    return export_path


def test_scan_path_detects_chatgpt_export(tmp_path: Path):
    _write_chatgpt_export(tmp_path)
    report = scan_path(str(tmp_path))
    kinds = [s.kind for s in report.sources]
    assert "chatgpt_export" in kinds


def test_extract_from_path_reads_chatgpt_export(tmp_path: Path):
    _write_chatgpt_export(tmp_path)
    signals = extract_from_path(str(tmp_path))
    assert any(signal.source_kind == "chatgpt_export" for signal in signals)
    user_msgs = next(signal.messages for signal in signals if signal.source_kind == "chatgpt_export")
    assert any("Python" in msg and "Rust" in msg for msg in user_msgs)


def test_infer_profile_detects_languages_and_style(tmp_path: Path):
    signals = [
        {
            "source_kind": "chatgpt_export",
            "source_path": str(tmp_path / "chatgpt_export.json"),
            "messages": ["I love Python and Rust.", "Use functional programming."],
            "timestamps": ["2026-06-05T23:30:00Z"],
            "code_extensions": [".py", ".rs"],
            "bookmarks": [],
        }
    ]
    profile = infer_profile(signals)
    assert "Python" in profile.persona.technical.primary_languages
    assert "Rust" in profile.persona.technical.primary_languages
    assert profile.persona.technical.coding_style == "functional"
    assert profile.persona.temporal.work_rhythm == "night_owl"
    provenance = profile.extra.get("x_provenance", {})
    assert provenance["technical.primary_languages"]["confidence"] == 0.6
    assert provenance["communication.tone"]["confidence"] > 0
    complete = completeness(profile)
    assert complete["present_count"] == complete["field_count"]


def test_extract_scrubs_secret_tokens(tmp_path: Path):
    export_path = tmp_path / "chatgpt_export.json"
    export_path.write_text(
        json.dumps(
            [
                {
                    "create_time": "2026-06-05T23:30:00Z",
                    "messages": [{"role": "user", "content": "my api token=sk-1234567890abcdef"}],
                }
            ]
        ),
        encoding="utf-8",
    )
    signals = extract_from_path(str(tmp_path))
    assert any(signal.source_kind == "chatgpt_export" for signal in signals)
    messages = next(signal.messages for signal in signals if signal.source_kind == "chatgpt_export")
    assert all("sk-1234567890abcdef" not in text for text in messages)
