"""
AID CLI — 入口

安装后可通过 `aid` 命令调用。

用法：
    aid identity init|show|sign|verify    # 身份管理
    aid social friend|chat|list|...       # 社交管理
    aid brain awake|sleep|think|...       # 大脑控制
"""

import typer

from alpha_id.brain_cli import brain_app
from alpha_id.identity_cli import identity_app
from alpha_id.network_cli import network_app
from alpha_id.repo_cli import repo_app
from alpha_id.scaffold_cli import scaffold_app
from alpha_id.skill_cli import skill_app
from alpha_id.social_cli import social_app

app = typer.Typer(help="AID — Agent Identity Layer")
app.add_typer(identity_app, name="identity")
app.add_typer(social_app, name="social")
app.add_typer(brain_app, name="brain")
app.add_typer(skill_app, name="skill")
app.add_typer(repo_app, name="repo")
app.add_typer(network_app, name="network")
app.add_typer(scaffold_app, name="scaffold")


@app.callback()
def main():
    """AID: Agent 身份层工具"""
    pass


if __name__ == "__main__":
    app()
