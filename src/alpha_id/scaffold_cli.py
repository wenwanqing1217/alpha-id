"""CLI — scaffold 子命令：为新项目生成开发环境配置

用法：
    aid scaffold <path> [--name NAME] [--desc DESC] [--force]
"""

from pathlib import Path

import typer

from alpha_id.scaffold_templates import (
    CONTRIBUTING,
    DEV_SETUP_BAT,
    EDITORCONFIG,
    GITHUB_CI,
    GITIGNORE,
    PRE_COMMIT_CONFIG,
    VSCODE_EXTENSIONS,
    VSCODE_SETTINGS,
    VSCODE_TASKS,
    generate_pyproject_toml,
)

scaffold_app = typer.Typer(help="为项目生成 Python 开发脚手架")


def _write_file(path: Path, content: str, force: bool = False) -> bool:
    """写入文件，跳过已存在的（除非 force）。返回 True 表示写入了。"""
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _report(paths_created: list[Path], paths_skipped: list[Path]):
    """打印报告"""
    if paths_created:
        typer.echo("\n✅ 已创建:")
        for p in sorted(paths_created):
            rel = p.name
            typer.echo(f"   📄 {rel}")
    if paths_skipped:
        typer.echo("\n⏭️  已存在（跳过）:")
        for p in sorted(paths_skipped):
            rel = p.name
            typer.echo(f"   📄 {rel}")

    if paths_skipped:
        typer.echo("\n💡 使用 --force 覆盖已存在的文件")


@scaffold_app.callback()
def main():
    pass


@scaffold_app.command("init")
def scaffold_init(
    path: str = typer.Argument(..., help="项目目录路径"),
    name: str = typer.Option("", "--name", "-n", help="项目名称（自动从目录名推断）"),
    desc: str = typer.Option("", "--desc", "-d", help="项目描述"),
    force: bool = typer.Option(False, "--force", "-f", help="覆盖已存在的文件"),
    skip_git: bool = typer.Option(False, "--skip-git", help="跳过 .gitignore"),
):
    """在新项目目录生成完整的开发环境脚手架"""
    # 处理 typer.Option 的默认值（直接函数调用时 typer 不转换）
    _unwrapped = [v.default if hasattr(v, "default") else v for v in (name, desc, force, skip_git)]
    name, desc, force, skip_git = _unwrapped
    root = Path(path).resolve()
    project_name = name or root.name

    typer.echo(f"🚀 正在为项目 '{project_name}' 生成脚手架...")
    typer.echo(f"   目标: {root}")

    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        typer.echo(f"   📁 已创建目录: {root}")

    created: list[Path] = []
    skipped: list[Path] = []

    files: list[tuple[str, str]] = [
        (".editorconfig", EDITORCONFIG),
        (".gitignore", GITIGNORE if not skip_git else ""),
        (".pre-commit-config.yaml", PRE_COMMIT_CONFIG),
        ("pyproject.toml", generate_pyproject_toml(project_name, desc)),
        ("CONTRIBUTING.md", CONTRIBUTING),
        ("scripts/dev_setup.bat", DEV_SETUP_BAT),
        (".github/workflows/ci.yml", GITHUB_CI),
        (".vscode/settings.json", VSCODE_SETTINGS),
        (".vscode/extensions.json", VSCODE_EXTENSIONS),
        (".vscode/tasks.json", VSCODE_TASKS),
    ]

    for rel_path, content in files:
        if not content:
            continue
        fp = root / rel_path
        ok = _write_file(fp, content, force=force)
        if ok:
            (created if content else skipped).append(fp)
        else:
            skipped.append(fp)

    # 创建 src/ 和 tests/ 骨架
    src_init = root / "src" / project_name.replace("-", "_") / "__init__.py"
    tests_init = root / "tests" / "__init__.py"

    for fp in (src_init, tests_init):
        if _write_file(fp, "", force=False):
            created.append(fp)

    _report(created, skipped)

    typer.echo("\n🎉 脚手架已生成！")
    typer.echo("\n📋 下一步:")
    typer.echo(f"   cd {root}")
    typer.echo("   scripts\\dev_setup.bat")
    typer.echo("   pip install -e .")
    typer.echo("   git init && git add . && git commit -m 'chore: 初始化项目'")
