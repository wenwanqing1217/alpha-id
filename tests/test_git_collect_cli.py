"""Tests for aid collect git CLI."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from alpha_id.profile_cli import collect_app
from alpha_id.profile_schema import load_profile, profile_exists


@pytest.fixture
def runner():
    return CliRunner()


class TestCollectGit:
    def test_collect_git_saves_profile(self, tmp_path, runner, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / "main.py").write_text("print('hi')", encoding="utf-8")
        monkeypatch.chdir(repo)
        # 隔离数据目录，避免写入用户主目录 ~/.alpha-id（CI/沙箱无权限）
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

        result = runner.invoke(collect_app, ["git", "--path", str(repo)])
        assert result.exit_code == 0, result.output
        assert "[OK] Git 仓库痕迹已采集" in result.output
        assert "Python" in result.output

        assert profile_exists()
        profile = load_profile()
        assert profile is not None
        assert "Python" in profile.persona.technical.primary_languages
        assert "git" in profile.extra.get("x_collected_sources", [])

    def test_collect_git_missing_path(self, runner):
        result = runner.invoke(collect_app, ["git", "--path", str(Path("/nonexistent/git"))])
        assert result.exit_code != 0
        assert "路径不存在" in result.output
