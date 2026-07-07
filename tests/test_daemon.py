"""测试 daemon 后台服务 - 不依赖真实进程"""

from pathlib import Path

from alpha_id.profile_cli import cmd_daemon


def test_daemon_status_no_pid(tmp_path, monkeypatch):
    """没有 PID 文件时 status 应提示未运行"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from typer.testing import CliRunner
    from alpha_id.profile_cli import profile_app

    r = CliRunner().invoke(profile_app, ["daemon", "status"])
    assert "未运行" in r.stdout or "未在运行" in r.stdout


def test_daemon_stop_no_pid(tmp_path, monkeypatch):
    """没有 PID 文件时 stop 应提示未运行"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from typer.testing import CliRunner
    from alpha_id.profile_cli import profile_app

    r = CliRunner().invoke(profile_app, ["daemon", "stop"])
    assert "未在运行" in r.stdout


def test_daemon_stale_pid(tmp_path, monkeypatch):
    """PID 文件存在但进程已死应优雅处理"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    pid_dir = tmp_path / ".alpha-id"
    pid_dir.mkdir(parents=True, exist_ok=True)
    (pid_dir / "daemon.pid").write_text("999999")  # 不存在的 PID
    from typer.testing import CliRunner
    from alpha_id.profile_cli import profile_app

    r = CliRunner().invoke(profile_app, ["daemon", "stop"])
    assert "已停止" in r.stdout or "进程不存在" in r.stdout
    assert not (pid_dir / "daemon.pid").exists()


def test_daemon_help():
    from typer.testing import CliRunner
    from alpha_id.profile_cli import profile_app

    r = CliRunner().invoke(profile_app, ["daemon", "--help"])
    assert r.exit_code == 0
    assert "start" in r.stdout
    assert "stop" in r.stdout
    assert "status" in r.stdout
