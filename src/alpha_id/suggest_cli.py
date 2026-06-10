"""Suggest — 推荐下一个导入的数据源"""

import logging
from pathlib import Path

import typer

logger = logging.getLogger(__name__)
app = typer.Typer(help="数据源推荐")

# 所有已知数据源
ALL_SOURCES = {
    "chatgpt": {
        "name": "ChatGPT",
        "file": "chatgpt_export.zip",
        "command": "aid collect chatgpt <zip>",
        "desc": "OpenAI ChatGPT 对话历史",
        "priority": 1,
    },
    "claude": {
        "name": "Claude",
        "file": "claude_export.zip",
        "command": "aid collect claude <zip>",
        "desc": "Anthropic Claude 对话历史",
        "priority": 2,
    },
    "cursor": {
        "name": "Cursor",
        "file": "",
        "command": "aid collect cursor <file>",
        "desc": "Cursor IDE 编程对话",
        "priority": 3,
    },
}


@app.command("list")
def cmd_list():
    """列出所有可导入的数据源"""
    profile_dir = Path.home() / ".alpha-id" / "profile" / "v0.1"
    identity_file = profile_dir / "identity.yaml"

    # 判断哪些已导入（简单检查：profile 文件存在即为有数据）
    has_profile = identity_file.exists()

    typer.echo("可导入的数据源:\n")
    for key, src in sorted(ALL_SOURCES.items(), key=lambda x: x[1]["priority"]):
        imported = "[ ]"
        if has_profile:
            if src["priority"] <= 2:
                imported = "[x]"
        typer.echo(f"  {imported} [{key}] {src['name']}")
        typer.echo(f"     {src['desc']}")
        if src["command"] and src["command"] != "TODO":
            typer.echo(f"     -> {src['command']}")
        else:
            typer.echo("     -> (尚未支持)")
        typer.echo("")

    typer.echo("建议: 按优先级从高到低导入")


@app.command("next")
def cmd_next():
    """推荐下一个要导入的数据源"""
    profile_dir = Path.home() / ".alpha-id" / "profile" / "v0.1"
    has_profile = profile_dir.exists() and any(profile_dir.iterdir())

    imported = []
    if has_profile:
        imported.append("chatgpt")
        # 如果 profile 有足够内容就认为 claude 也导入了
        imported.append("claude")

    for key, src in sorted(ALL_SOURCES.items(), key=lambda x: x[1]["priority"]):
        if key not in imported:
            if src["command"] and src["command"] != "TODO":
                typer.echo(f"[推荐] 下一个导入: {src['name']}")
                typer.echo(f"  {src['desc']}")
                typer.echo(f"  {src['command']}")
            else:
                typer.echo(f"[提示] {src['name']} 开发中，暂时无法导入")
            return

    typer.echo("[OK] 所有数据源已导入或开发中")
