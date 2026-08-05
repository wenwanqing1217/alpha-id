"""
AID CLI — 把你的数字痕迹收回来 + 对话即 DIY 你的工作台

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
    aid diy chat "同步飞书通讯录"     对话即实现：自然语言 → 自动找工具执行
    aid diy repl                     进入 DIY REPL，连续对话
    aid diy intents                  列出 DIY 支持的所有意图
"""

import typer

from alpha_id.agent_cli import app as agent_app
from alpha_id.detect import format_report, scan
from alpha_id.diy_cli import diy_app
from alpha_id.identity_cli import identity_app
from alpha_id.profile_cli import cmd_init, collect_app, profile_app
from alpha_id.profile_wizard import wizard_app
from alpha_id.scaffold_cli import scaffold_app
from alpha_id.skill_cli import skill_app
from alpha_id.social_cli import social_app
from alpha_id.suggest_cli import app as suggest_app

app = typer.Typer(help="Alpha-ID — 你的数字灵魂 + DIY 工作台")
app.command("init")(cmd_init)
app.add_typer(identity_app, name="identity")
app.add_typer(social_app, name="social")
app.add_typer(skill_app, name="skill")
app.add_typer(profile_app, name="profile")
app.add_typer(agent_app, name="agent")
app.add_typer(collect_app, name="collect")
app.add_typer(wizard_app, name="wizard")
app.add_typer(suggest_app, name="suggest")
app.add_typer(scaffold_app, name="scaffold")
app.add_typer(diy_app, name="diy")


@app.command("chat")
def chat_shortcut(
    prompt: str = typer.Argument(..., help="自然语言：你想让 Alpha-ID 帮你做什么"),
    alpha_id: str = typer.Option("Alpha-001", "--alpha-id", "-a"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n"),
    use_local_parser: bool = typer.Option(False, "--local"),
):
    """✨ 超短入口：`aid chat "xxx"` 等于 `aid diy chat xxx`（对话即实现）"""
    from alpha_id.diy_cli import diy_chat
    diy_chat(
        prompt=prompt,
        alpha_id=alpha_id,
        dry_run=dry_run,
        use_local_parser=use_local_parser,
    )


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
