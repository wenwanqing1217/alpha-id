"""
AID CLI — 把你的数字痕迹收回来

安装后可通过 `aid` 命令调用。

用法：
    aid init                         初始化数字身份
    aid detect                      扫描本机有哪些数据可以采集
    aid collect chatgpt <zip>        从 ChatGPT 导入
    aid collect trae                 从 Trae 取回代码痕迹
    aid profile show                 查看你的数字画像
    aid profile web                  浏览器查看画像卡片
    aid profile mine --path .        从本机痕迹扫描并生成画像
    aid wizard start                 3 个问题生成画像
"""

import typer

from alpha_id.agent_cli import app as agent_app
from alpha_id.detect import format_report, scan
from alpha_id.identity_cli import identity_app
from alpha_id.profile_cli import cmd_init, collect_app, profile_app
from alpha_id.profile_wizard import wizard_app
from alpha_id.skill_cli import skill_app
from alpha_id.social_cli import social_app
from alpha_id.suggest_cli import app as suggest_app

app = typer.Typer(help="Alpha-ID — 你的数字灵魂")
app.command("init")(cmd_init)
app.add_typer(identity_app, name="identity")
app.add_typer(social_app, name="social")
app.add_typer(skill_app, name="skill")
app.add_typer(profile_app, name="profile")
app.add_typer(agent_app, name="agent")
app.add_typer(collect_app, name="collect")
app.add_typer(wizard_app, name="wizard")
app.add_typer(suggest_app, name="suggest")


@app.command()
def detect():
    """扫描本机数据源，找到散落的数字痕迹"""
    found = scan()
    out = format_report(found)
    print(out)


@app.callback()
def main():
    """Alpha-ID: 数字身份层"""
    pass


if __name__ == "__main__":
    app()
