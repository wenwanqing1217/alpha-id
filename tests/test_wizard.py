"""测试画像向导"""

from typer.testing import CliRunner
from alpha_id.profile_wizard import wizard_app

runner = CliRunner()


def test_wizard_help():
    r = runner.invoke(wizard_app, ["--help"])
    assert r.exit_code == 0
    assert "start" in r.stdout
