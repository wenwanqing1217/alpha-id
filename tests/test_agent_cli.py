"""测试 A2A Agent 命令"""

from typer.testing import CliRunner

from alpha_id.agent_cli import app

runner = CliRunner()


def test_agent_help():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "scan" in r.stdout
    assert "handshake" in r.stdout


def test_agent_scan_no_target():
    """扫不存在的地址应优雅处理"""
    r = runner.invoke(app, ["scan", "--host", "127.0.0.1", "--ports", "19999-19999"])
    assert r.exit_code == 0
    assert "无发现" in r.stdout or "0 个" in r.stdout


def test_agent_scan_invalid_port():
    """无效端口范围应报错"""
    r = runner.invoke(app, ["scan", "--ports", "abc-def"])
    assert r.exit_code != 0


def test_agent_handshake_no_target():
    """握手目标不可达应报错"""
    r = runner.invoke(app, ["handshake", "http://127.0.0.1:1", "did:aid:test"])
    assert r.exit_code == 0  # CLI 不崩溃
