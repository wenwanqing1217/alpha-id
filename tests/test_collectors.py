"""
Alpha-ID 采集器测试 — Browser 内部函数测试（trae 依赖真实目录暂不 mock）
"""

import json
from pathlib import Path

import pytest

# 测试 Browser 采集器的内部函数（它们接受 path 参数）
from alpha_id.collectors.browser import _read_bookmarks
from alpha_id.collectors.browser import _read_history


# ── Browser 书签采集器测试 ──


class TestBrowserBookmarks:
    """浏览器书签解析测试"""

    def _make_bookmarks_json(self, tmp_path, bookmarks_data=None):
        """构造模拟的 Chrome 书签 JSON 文件"""
        if bookmarks_data is None:
            bookmarks_data = {
                "roots": {
                    "bookmark_bar": {
                        "children": [
                            {"name": "GitHub", "url": "https://github.com", "type": "url"},
                            {"name": "Python", "url": "https://docs.python.org", "type": "url"},
                        ],
                        "type": "folder",
                    },
                    "other": {
                        "children": [
                            {"name": "Stack Overflow", "url": "https://stackoverflow.com", "type": "url"},
                        ],
                        "type": "folder",
                    },
                }
            }
        bm_file = tmp_path / "Default" / "Bookmarks"
        bm_file.parent.mkdir(parents=True, exist_ok=True)
        bm_file.write_text(json.dumps(bookmarks_data, ensure_ascii=False), encoding="utf-8")
        return bm_file.parent

    def test_read_bookmarks_returns_list(self, tmp_path):
        """读取书签应返回书签列表"""
        path = self._make_bookmarks_json(tmp_path)
        result = _read_bookmarks(path)
        assert isinstance(result, list), "应返回列表"
        assert len(result) >= 3, "应包含 3 个书签"

    def test_read_bookmarks_has_fields(self, tmp_path):
        """每个书签应包含 name, url, folder"""
        path = self._make_bookmarks_json(tmp_path)
        result = _read_bookmarks(path)
        bm = result[0]
        assert "name" in bm, "应包含 name"
        assert "url" in bm, "应包含 url"
        assert bm["url"].startswith("http"), "url 应为有效链接"

    def test_read_bookmarks_empty(self, tmp_path):
        """空书签文件应返回空列表"""
        path = tmp_path / "Default"
        path.mkdir(parents=True)
        bm_file = path / "Bookmarks"
        bm_file.write_text("{}", encoding="utf-8")
        result = _read_bookmarks(path)
        assert result == [], "空书签应返回空列表"

    def test_read_bookmarks_no_file(self, tmp_path):
        """没有书签文件应返回空列表"""
        path = tmp_path / "Default"
        path.mkdir(parents=True)
        result = _read_bookmarks(path)
        assert result == [], "无书签文件应返回空列表"


# ── Browser 历史采集器测试（依赖 SQLite，验证基本不崩） ──


class TestBrowserHistory:
    """浏览器历史解析测试（基本路径）"""

    def test_read_history_no_file(self, tmp_path):
        """没有历史文件应返回空列表"""
        path = tmp_path / "Default"
        path.mkdir(parents=True)
        result = _read_history(path)
        assert result == [], "无历史文件应返回空列表"

    def test_read_history_invalid_file(self, tmp_path):
        """损坏的历史文件应返回空列表"""
        path = tmp_path / "Default"
        path.mkdir(parents=True)
        bad_file = path / "History"
        bad_file.write_text("not a database file", encoding="utf-8")
        result = _read_history(path)
        assert result == [], "损坏文件应返回空列表"


# ── Git 采集器测试 ──


class TestGitCollector:
    """Git 仓库采集器测试"""

    def test_detect_finds_repo(self, tmp_path, monkeypatch):
        monkeypatch.setattr("alpha_id.collectors.git.Path.home", lambda: tmp_path)
        monkeypatch.setattr("alpha_id.collectors.git.Path.cwd", lambda: tmp_path)
        repo = tmp_path / "projects" / "myapp"
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()
        (repo / "main.py").write_text("print('hi')", encoding="utf-8")

        from alpha_id.collectors.git import GitCollector

        assert GitCollector().detect() is True

    def test_collect_returns_profile(self, tmp_path, monkeypatch):
        monkeypatch.setattr("alpha_id.collectors.git.Path.home", lambda: tmp_path)
        monkeypatch.setattr("alpha_id.collectors.git.Path.cwd", lambda: tmp_path)
        repo = tmp_path / "projects" / "myapp"
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()
        (repo / "main.py").write_text("print('hi')", encoding="utf-8")
        (repo / "app.tsx").write_text("export default () => <div/>", encoding="utf-8")

        from alpha_id.collectors.git import GitCollector

        profile = GitCollector().collect()
        assert profile is not None
        assert "Python" in profile.persona.technical.primary_languages
        assert "TypeScript" in profile.persona.technical.primary_languages
