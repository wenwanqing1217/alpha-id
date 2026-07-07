"""测试 Cursor 采集器 - 边界情况"""

import json, zipfile, pytest
from pathlib import Path

from alpha_id.collectors.cursor import collect


def test_cursor_empty_zip(tmp_path):
    """空 ZIP 应返回 None"""
    z = tmp_path / "empty.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("data.json", "[]")
    assert collect(z) is None


def test_cursor_invalid_file(tmp_path):
    """无效文件应返回 None"""
    f = tmp_path / "not_a_zip.txt"
    f.write_text("not a zip")
    assert collect(f) is None


def test_cursor_not_found():
    """不存在的文件应返回 None"""
    assert collect(Path("/nonexistent/cursor.zip")) is None


def test_cursor_minimal_data(tmp_path):
    """最少 3 条对话才能生成画像"""
    z = tmp_path / "cursor.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(
            "conversations.json",
            json.dumps(
                [
                    {"text": "hello", "timestamp": "2026-01-01T10:00:00Z"},
                ]
            ),
        )
    assert collect(z) is None


def test_cursor_valid_data(tmp_path):
    """3 条以上对话应生成画像"""
    z = tmp_path / "cursor_valid.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(
            "conversations.json",
            json.dumps(
                [
                    {"text": "Python 和 Rust 怎么选？", "timestamp": "2026-01-01T10:00:00Z"},
                    {"text": "用 functional 风格重构", "timestamp": "2026-01-01T11:00:00Z"},
                    {"text": "这个 bug 调了一晚上了", "timestamp": "2026-01-01T22:00:00Z"},
                ]
            ),
        )
    p = collect(z)
    assert p is not None
    assert "Python" in p.persona.technical.primary_languages


def test_cursor_sqlite_fallback(tmp_path):
    """不是 ZIP 但 SQLite 文件应优雅降级"""
    f = tmp_path / "cursor.db"
    f.write_text("not actually a sqlite db")  # 非法 SQLite
    assert collect(f) is None  # 降级返回 None 而不是崩溃
