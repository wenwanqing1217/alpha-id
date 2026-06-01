"""CLI — repo 子命令：去中心化技能仓库管理

用法：
    aid repo init <path> --name NAME [--desc DESC]
    aid repo scan <path>
    aid repo publish <path> <file> --name NAME [--version VER] [--desc DESC]
    aid repo install <path> <name>
    aid repo info <path>
"""

from typing import Optional

import typer

from alpha_id.signer import AIDSigner
from alpha_id.skill_repository import SkillRepository
from alpha_id.skill_signer import SkillRegistry

repo_app = typer.Typer(help="去中心化技能仓库")


def _get_signer(require: bool = True) -> AIDSigner:
    signer = AIDSigner()
    try:
        signer.load_from_aid_dir()
    except FileNotFoundError:
        if require:
            typer.echo("❌ 未找到身份。请先运行: aid identity init", err=True)
            raise typer.Exit(1)
    return signer


def _get_repo() -> SkillRepository:
    return SkillRepository()


# ── init ──


@repo_app.command()
def init(
    path: str = typer.Argument(..., help="仓库目录路径"),
    name: str = typer.Option(..., "--name", "-n", help="仓库名称"),
    desc: str = typer.Option("", "--desc", "-d", help="仓库描述"),
):
    """初始化一个新的技能仓库目录"""
    signer = _get_signer(require=False)
    author_did = signer.did if signer.has_identity else ""
    repo = _get_repo()
    meta = repo.init_repo(path, name=name, description=desc, author_did=author_did)
    typer.echo(f"✅ 仓库已初始化: {path}")
    typer.echo(f"   名称: {meta.name}")
    if meta.author_did:
        typer.echo(f"   作者: {meta.author_did}")


# ── scan ──


@repo_app.command()
def scan(
    path: str = typer.Argument(..., help="仓库目录路径"),
):
    """扫描仓库中的可用技能"""
    repo = _get_repo()
    skills = repo.scan(path)
    if not skills:
        typer.echo("📭 仓库中未发现技能")
        return
    typer.echo(f"📋 发现 {len(skills)} 个技能:")
    typer.echo(f"{'名称':<24} {'版本':<10} {'已签名':<8} {'描述'}")
    typer.echo("-" * 70)
    for s in sorted(skills, key=lambda x: x.name):
        signed = "✓" if s.is_signed else "✗"
        desc_short = s.description[:36] if s.description else ""
        typer.echo(f"{s.name:<24} {s.version:<10} {signed:<8} {desc_short}")


# ── publish ──


@repo_app.command()
def publish(
    path: str = typer.Argument(..., help="仓库目录路径"),
    file: str = typer.Argument(..., help="技能文件路径"),
    name: str = typer.Option(..., "--name", "-n", help="技能名称"),
    version: str = typer.Option("1.0.0", "--version", "-v", help="版本号"),
    desc: str = typer.Option("", "--desc", "-d", help="技能描述"),
    force: bool = typer.Option(False, "--force", "-f", help="覆盖已有技能"),
):
    """签名并发布技能到仓库"""
    signer = _get_signer(require=True)
    repo = _get_repo()
    skill = repo.publish_skill(
        path,
        file,
        signer,
        name=name,
        version=version,
        description=desc,
        force=force,
    )
    typer.echo(f"✅ 技能已发布: {skill.name}@{skill.version}")
    typer.echo(f"   文件: {skill.skill_file}")


# ── install ──


@repo_app.command()
def install(
    path: str = typer.Argument(..., help="仓库目录路径"),
    name: str = typer.Argument(..., help="技能名称"),
    registry_path: Optional[str] = typer.Option(None, "--registry", help="注册表目录（默认 ~/.aid/skills）"),
):
    """从仓库安装技能到本地注册表"""
    repo = _get_repo()
    reg = SkillRegistry(storage_dir=registry_path or "~/.aid/skills")
    skills = repo.scan(path)
    matches = [s for s in skills if s.name == name]
    if not matches:
        typer.echo(f"❌ 仓库中未找到技能: {name}")
        raise typer.Exit(1)
    result = repo.install_skill(matches[0], reg)
    if result.get("success"):
        typer.echo(f"✅ 技能已安装: {name}")
    else:
        typer.echo(f"❌ 安装失败: {result.get('message', '未知错误')}", err=True)
        raise typer.Exit(1)


# ── info ──


@repo_app.command()
def info(
    path: str = typer.Argument(..., help="仓库目录路径"),
):
    """查看仓库元数据"""
    repo = _get_repo()
    meta = repo.get_repo_meta(path)
    if meta is None:
        typer.echo("❌ 未找到仓库元数据")
        raise typer.Exit(1)
    typer.echo(f"📦 仓库: {meta.name}")
    typer.echo(f"   描述: {meta.description or '(无)'}")
    if meta.author_did:
        typer.echo(f"   作者: {meta.author_did}")
    typer.echo(f"   技能数: {len(meta.skills)}")
    typer.echo(f"   协议版本: {meta.version}")
