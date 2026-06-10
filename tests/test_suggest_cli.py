"""测试 Suggest 推荐"""
from typer.testing import CliRunner
from alpha_id.suggest_cli import app

runner = CliRunner()


def test_suggest_help():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "list" in r.stdout
    assert "next" in r.stdout


def test_suggest_list_contains_all():
    r = runner.invoke(app, ["list"])
    assert r.exit_code == 0
    assert "chatgpt" in r.stdout.lower() or "ChatGPT" in r.stdout
    assert "claude" in r.stdout.lower() or "Claude" in r.stdout
    assert "cursor" in r.stdout.lower() or "Cursor" in r.stdout


def test_suggest_next_returns_something():
    r = runner.invoke(app, ["next"])
    assert r.exit_code == 0
    # 无论是否有 profile，都不应该崩溃
    assert len(r.stdout) > 0
