"""
CLI 集成测试 — 同进程运行，monkeypatch Path.home()
"""

import json
import os
import sys
import pytest
from pathlib import Path
from typer.testing import CliRunner


runner = CliRunner()


@pytest.fixture
def clean_cli(tmp_path, monkeypatch):
    """在隔离 HOME 中运行 CLI（monkeypatch Path.home + env vars + 重载模块）"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # 清除已导入的 CLI 模块缓存，使 Path.home() 重新计算
    for mod in list(sys.modules.keys()):
        if mod.startswith("alpha_id.") or mod in (
            "alpha_id.identity_cli",
            "alpha_id.skill_cli",
            "alpha_id.social_cli",
            "alpha_id.cli",
        ):
            del sys.modules[mod]
    from alpha_id.cli import app

    return app, tmp_path


def invoke(clean_cli, args):
    app, _ = clean_cli
    return runner.invoke(app, args)


def test_help(clean_cli):
    r = invoke(clean_cli, ["--help"])
    assert r.exit_code == 0
    assert "identity" in r.stdout
    assert "social" in r.stdout
    assert "profile" in r.stdout
    assert "skill" in r.stdout


class TestIdentity:
    def test_help(self, clean_cli):
        r = invoke(clean_cli, ["identity", "--help"])
        assert r.exit_code == 0
        assert "init" in r.stdout
        assert "show" in r.stdout
        assert "sign" in r.stdout
        assert "verify" in r.stdout

    def test_init_show(self, clean_cli):
        app, tmp_home = clean_cli
        aid_dir = tmp_home / ".aid"

        r = invoke(clean_cli, ["identity", "init", "--force"])
        assert r.exit_code == 0, f"init failed: {r.stdout} {r.stderr}"

        assert (aid_dir / "identity.priv").exists(), f"not in {aid_dir}"
        assert (aid_dir / "identity.pub").exists()
        assert (aid_dir / "identity.did").exists()
        assert (aid_dir / "identity.doc.json").exists()

        did_text = (aid_dir / "identity.did").read_text().strip()
        assert did_text.startswith("did:aid:")

        r2 = invoke(clean_cli, ["identity", "show"])
        assert r2.exit_code == 0
        assert did_text in r2.stdout

    def test_sign_verify(self, clean_cli):
        _, tmp_home = clean_cli
        invoke(clean_cli, ["identity", "init", "--force"])

        test_file = tmp_home / "hello.txt"
        test_file.write_text("Hello, AID!")

        r = invoke(clean_cli, ["identity", "sign", str(test_file)])
        assert r.exit_code == 0, f"sign: {r.stdout}"

        r = invoke(clean_cli, ["identity", "verify", str(test_file)])
        assert r.exit_code == 0, f"verify: {r.stdout}"
        assert "验证通过" in r.stdout

    def test_export_import(self, clean_cli):
        _, tmp_home = clean_cli
        invoke(clean_cli, ["identity", "init", "--force"])

        original_did = (tmp_home / ".aid" / "identity.did").read_text().strip()

        bundle_path = tmp_home / "my-id.json"
        r = invoke(clean_cli, ["identity", "export", "--output", str(bundle_path), "--password", "test123"])
        assert r.exit_code == 0, f"export: {r.stdout}"
        assert bundle_path.exists()

        # 删除原身份
        for f in ["identity.priv", "identity.pub", "identity.did", "identity.doc.json"]:
            (tmp_home / ".aid" / f).unlink()

        r = invoke(clean_cli, ["identity", "import-bundle", str(bundle_path), "--password", "test123"])
        assert r.exit_code == 0, f"import: {r.stdout}"

        restored_did = (tmp_home / ".aid" / "identity.did").read_text().strip()
        assert restored_did == original_did


class TestSocial:
    def test_help(self, clean_cli):
        r = invoke(clean_cli, ["social", "--help"])
        assert r.exit_code == 0
        assert "friend" in r.stdout
        assert "chat" in r.stdout
        assert "messages" in r.stdout


class TestSkill:
    def test_help(self, clean_cli):
        r = invoke(clean_cli, ["skill", "--help"])
        assert r.exit_code == 0
        assert "sign" in r.stdout
        assert "verify" in r.stdout
        assert "list" in r.stdout
        assert "info" in r.stdout
        assert "revoke" in r.stdout
        assert "run" in r.stdout
        assert "stats" in r.stdout
        assert "poe" in r.stdout

    def test_list_empty(self, clean_cli):
        r = invoke(clean_cli, ["skill", "list"])
        assert r.exit_code == 0
        assert "空" in r.stdout or "📭" in r.stdout

    def test_full_flow(self, clean_cli):
        """
        全流程：init → skill sign + register → list → info → run → stats → revoke
        """
        _, tmp_home = clean_cli
        invoke(clean_cli, ["identity", "init", "--force"])

        skill_file = tmp_home / "greet.py"
        skill_file.write_text('def main(p): return "Hello, " + p.get("name", "World")')

        r = invoke(
            clean_cli, ["skill", "sign", str(skill_file), "--name", "greet", "--desc", "打招呼技能", "--register"]
        )
        assert r.exit_code == 0, f"sign: {r.stdout} {r.stderr}"
        assert "签名成功" in r.stdout or "✅" in r.stdout

        r = invoke(clean_cli, ["skill", "list"])
        assert r.exit_code == 0
        assert "greet" in r.stdout

        r = invoke(clean_cli, ["skill", "info", "greet"])
        assert r.exit_code == 0
        assert "greet" in r.stdout

        r = invoke(clean_cli, ["skill", "run", "greet", '{"name":"CLI"}', "--as-did", "did:aid:test-executor"])
        assert r.exit_code == 0, f"run: {r.stdout} {r.stderr}"
        # 安全模式：text 类型直接返回文件原文，不再执行代码
        assert "def main(p)" in r.stdout or "Hello" in r.stdout

        r = invoke(clean_cli, ["skill", "stats", "leaderboard"])
        assert r.exit_code == 0
        assert "🏆" in r.stdout or "排行榜" in r.stdout

        r = invoke(clean_cli, ["skill", "revoke", "greet", "--reason", "测试吊销"])
        assert r.exit_code == 0, f"revoke: {r.stdout} {r.stderr}"

    def test_info_nonexistent(self, clean_cli):
        r = invoke(clean_cli, ["skill", "info", "nonexistent"])
        assert r.exit_code != 0

    def test_stats_bad_subcmd(self, clean_cli):
        r = invoke(clean_cli, ["skill", "stats", "invalid"])
        assert r.exit_code != 0
