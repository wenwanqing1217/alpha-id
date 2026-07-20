"""
CLI — skill 子命令

用法：
    aid skill sign <file> [--name NAME] [--version VERSION] [--desc DESC] [--type TYPE] [--tags TAGS]
    aid skill verify <file> <package.json>
    aid skill list
    aid skill info <name> [--version VERSION]
    aid skill revoke <name> [--reason REASON]
    aid skill registry <path>
"""

from pathlib import Path
from typing import Optional

import typer

from alpha_id.signer import AIDSigner
from alpha_id.skill_signer import (
    SkillAttributionTracker,
    SkillPackage,
    SkillRegistry,
    SkillSigningError,
    sign_skill,
    verify_skill,
)
from core.reputation import SkillReputation

skill_app = typer.Typer(help="技能签名与验证")

# 默认注册表路径
DEFAULT_REGISTRY_DIR = "~/.aid/skills"


def _get_signer(require: bool = True) -> AIDSigner:
    """获取（并确保已加载身份）"""
    signer = AIDSigner()
    try:
        signer.load_from_aid_dir()
    except FileNotFoundError:
        if require:
            typer.echo("❌ 未找到身份。请先运行: aid identity init", err=True)
            raise typer.Exit(1)
    return signer


def _get_registry(path: Optional[str] = None) -> SkillRegistry:
    return SkillRegistry(storage_dir=path or DEFAULT_REGISTRY_DIR, signer=_get_signer(require=False))


# ── sign ──


@skill_app.command("sign")
def cmd_sign(
    file: str = typer.Argument(..., help="技能文件路径"),
    name: str = typer.Option("", "--name", "-n", help="技能名称（默认用文件名）"),
    version: str = typer.Option("1.0.0", "--version", "-v", help="语义版本号"),
    desc: str = typer.Option("", "--desc", "-d", help="技能描述"),
    content_type: str = typer.Option("text", "--type", "-t", help="内容类型"),
    tags: str = typer.Option("", "--tags", help="标签，逗号分隔"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出签名包路径"),
    register: bool = typer.Option(False, "--register", "-r", help="签名后注册到本地注册表"),
):
    """对技能文件签名，生成 SkillPackage JSON"""
    signer = _get_signer(require=True)
    fpath = Path(file).expanduser()

    skill_name = name or fpath.stem
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    try:
        pkg = sign_skill(
            skill_file=fpath,
            signer=signer,
            name=skill_name,
            version=version,
            description=desc,
            content_type=content_type,
            tags=tag_list,
        )
    except (FileNotFoundError, SkillSigningError) as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)

    # 输出
    out_path = output or f"{fpath}.skill.json"
    pkg.save(out_path)

    typer.echo("✅ 签名成功")
    typer.echo(f"   技能: {pkg.name}@{pkg.version}")
    typer.echo(f"   作者: {pkg.author_did}")
    typer.echo(f"   文件: {out_path}")
    typer.echo(f"   摘要: {pkg.content_hash[:16]}...")

    if register:
        registry = _get_registry()
        try:
            content = fpath.read_bytes()
            result = registry.register(pkg, content=content)
            typer.echo(f"📦 已注册: {result['key']}")
        except SkillSigningError as e:
            typer.echo(f"⚠️  注册失败: {e}", err=True)


# ── verify ──


@skill_app.command("verify")
def cmd_verify(
    file: str = typer.Argument(..., help="技能文件路径"),
    package: str = typer.Argument(..., help="SkillPackage JSON 路径"),
    check_registry: bool = typer.Option(False, "--check-registry", help="查询注册表吊销状态"),
):
    """验证技能文件的签名"""
    pkg = SkillPackage.load(package)
    registry = _get_registry() if check_registry else None
    result = verify_skill(file, pkg, registry=registry)

    if result["valid"]:
        typer.echo("✅ 签名验证通过")
    else:
        typer.echo("❌ 签名验证失败")

    typer.echo(f"   作者: {result['author_did']}")
    typer.echo(f"   公钥: {result['author_public_key'][:16] if result.get('author_public_key') else 'N/A'}...")
    typer.echo(f"   内容匹配: {'✓' if result['content_match'] else '✗'}")
    typer.echo(f"   签名有效: {'✓' if result['signature_valid'] else '✗'}")
    if result.get("revoked") is not None:
        typer.echo(f"   吊销状态: {'已吊销' if result['revoked'] else '正常'}")

    if result["errors"]:
        for err in result["errors"]:
            typer.echo(f"   ⚠️  {err}", err=True)

    if not result["valid"]:
        raise typer.Exit(1)


# ── list ──


@skill_app.command("list")
def cmd_list(
    include_revoked: bool = typer.Option(False, "--all", "-a", help="包含已吊销的技能"),
    registry_path: Optional[str] = typer.Option(None, "--registry", help="注册表目录路径"),
):
    """列出本地注册的技能"""
    registry = _get_registry(registry_path)
    items = registry.list(include_revoked=include_revoked)

    if not items:
        typer.echo("📭 注册表为空")
        return

    typer.echo(f"📋 已注册技能 ({len(items)}):")
    typer.echo(f"{'名称':<24} {'版本':<10} {'作者':<30} {'类型':<10} {'状态'}")
    typer.echo("-" * 100)
    for s in sorted(items, key=lambda x: x["name"]):
        status = "✓ 已签名"
        if s["is_revoked"]:
            status = "⛔ 已吊销"
        name_short = s["name"][:22]
        did_short = s["author_did"][:28] + "..." if len(s["author_did"]) > 28 else s["author_did"]
        typer.echo(f"{name_short:<24} {s['version']:<10} {did_short:<30} {s['content_type']:<10} {status}")


# ── info ──


@skill_app.command("info")
def cmd_info(
    name: str = typer.Argument(..., help="技能名称"),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="版本号（默认最新）"),
    registry_path: Optional[str] = typer.Option(None, "--registry", help="注册表目录路径"),
):
    """查看技能详情"""
    registry = _get_registry(registry_path)
    pkg = registry.get(name, version=version)

    if pkg is None:
        typer.echo(f"❌ 未找到技能: {name}@{version or 'latest'}", err=True)
        raise typer.Exit(1)

    typer.echo(f"📄 {pkg.name}@{pkg.version}")
    typer.echo(f"   描述: {pkg.description or '(无描述)'}")
    typer.echo(f"   作者: {pkg.author_did}")
    typer.echo(f"   公钥: {pkg.author_public_key_hex[:16]}...")
    typer.echo(f"   类型: {pkg.content_type}")
    typer.echo(f"   哈希: {pkg.content_hash[:20]}...")
    typer.echo(f"   签名: {'✓' if pkg.is_signed else '✗'}")
    typer.echo(f"   时间: {pkg.signed_at}")
    typer.echo(f"   标签: {', '.join(pkg.tags) if pkg.tags else '(无)'}")
    typer.echo(f"   依赖: {', '.join(pkg.dependencies) if pkg.dependencies else '(无)'}")

    revoked = registry.is_revoked(pkg.name)
    if revoked:
        rev = registry.get_revocation(pkg.name)
        typer.echo(f"   ⛔ 已吊销: {rev.get('reason', '无原因')}")


# ── revoke ──


@skill_app.command("revoke")
def cmd_revoke(
    name: str = typer.Argument(..., help="技能名称"),
    reason: str = typer.Option("", "--reason", "-r", help="吊销原因"),
    registry_path: Optional[str] = typer.Option(None, "--registry", help="注册表目录路径"),
):
    """吊销一个技能（所有版本）"""
    signer = _get_signer(require=True)
    registry = _get_registry(registry_path)
    registry._signer = signer

    pkg = registry.get(name)
    if pkg is None:
        typer.echo(f"⚠️  注册表中未找到技能: {name}，仍将记录吊销", err=True)

    try:
        result = registry.revoke(name, reason=reason, signer=signer)
        typer.echo(f"⛔ 已吊销: {result['name']}")
        if reason:
            typer.echo(f"   原因: {reason}")
    except SkillSigningError as e:
        typer.echo(f"❌ 吊销失败: {e}", err=True)
        raise typer.Exit(1)


# ── run ──


@skill_app.command(name="run")
def run_skill(
    skill_name: str = typer.Argument(..., help="技能名称"),
    params_json: str = typer.Argument("{}", help="JSON 参数"),
    as_did: Optional[str] = typer.Option(None, "--as-did", help="执行者 DID（用于归因）"),
):
    """运行一个已注册的技能"""
    try:
        from alpha_id.skill_signer import SkillAttributionTracker, SkillRegistry, SkillRuntime

        registry = SkillRegistry(storage_dir=DEFAULT_REGISTRY_DIR)
        tracker = SkillAttributionTracker(storage_dir=DEFAULT_REGISTRY_DIR)
        runtime = SkillRuntime(registry, tracker=tracker)
        executor_did = as_did or ""
        result = runtime.execute(skill_name, params_json, executor_did=executor_did)
        typer.echo(result)
    except Exception as e:
        typer.echo(f"[错误] {e}", err=True)
        raise typer.Exit(code=1)


# ── stats ──


@skill_app.command("stats")
def cmd_stats(
    subcmd: str = typer.Argument(..., help="author <did> | skill <name> | me | leaderboard"),
    target: str = typer.Argument("", help="DID (author) 或 skill name"),
    days: int = typer.Option(30, "--days", "-d", help="统计天数"),
    top_n: int = typer.Option(10, "--top", "-t", help="排行榜人数"),
    registry_path: Optional[str] = typer.Option(None, "--registry", help="注册表目录路径"),
):
    """查看技能使用统计与作者信誉"""
    SkillRegistry(storage_dir=registry_path or DEFAULT_REGISTRY_DIR)
    tracker = SkillAttributionTracker(storage_dir=registry_path or DEFAULT_REGISTRY_DIR)

    if subcmd == "author" and target:
        stats = tracker.get_author_stats(target, days=days)
        report = SkillReputation.format_author_report(target, stats)
        typer.echo(report)

    elif subcmd == "skill" and target:
        stats = tracker.get_skill_stats(target, days=days)
        typer.echo(f"技能: {target}")
        typer.echo(f"总执行次数: {stats['total_executions']}")
        typer.echo(f"成功率: {stats['success_rate'] * 100:.1f}%")
        typer.echo(f"不同执行者: {stats['unique_executors']}")

    elif subcmd == "me":
        signer = _get_signer(require=False)
        if not signer or not signer.did:
            typer.echo("❌ 未找到当前身份", err=True)
            raise typer.Exit(1)
        stats = tracker.get_author_stats(signer.did, days=days)
        report = SkillReputation.format_author_report(signer.did, stats)
        typer.echo(report)

    elif subcmd == "leaderboard":
        board = tracker.get_authors_leaderboard(top_n=top_n, days=days)
        if not board:
            typer.echo("📭 暂无数据")
            return
        typer.echo(f"🏆 作者排行榜 (过去 {days} 天):")
        for i, entry in enumerate(board, 1):
            score = SkillReputation.compute(entry)
            level = SkillReputation.compute_level(score)
            did_short = entry["author_did"][:20] + "..." if len(entry["author_did"]) > 20 else entry["author_did"]
            typer.echo(
                f"{i:2d}. {did_short:<24} {entry['total_executions']:4d} 次 | 成功率 {entry['success_rate'] * 100:.0f}% | 信誉 {score:.0f}级{level}"
            )

    else:
        typer.echo("用法: aid skill stats author <did> | skill <name> | me | leaderboard", err=True)
        raise typer.Exit(1)


# ── poe ──


@skill_app.command("poe")
def cmd_poe(
    poe_id_or_sub: str = typer.Argument(..., help="PoE ID 或子命令: list/verify/chain"),
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="按技能过滤"),
    executor: Optional[str] = typer.Option(None, "--executor", "-e", help="按执行者过滤"),
    limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
    poe_dir: Optional[str] = typer.Option(None, "--poe-dir", help="PoE 存储目录"),
):
    """查看和验证执行证明（PoE）"""
    from alpha_id.poe import PoEStore

    store = PoEStore(storage_dir=poe_dir or DEFAULT_REGISTRY_DIR)

    if poe_id_or_sub == "list":
        if skill:
            poes = store.list_for_skill(skill, limit=limit)
        elif executor:
            poes = store.list_for_executor(executor, limit=limit)
        else:
            poes = store.list_all(limit=limit)

        if not poes:
            typer.echo("📭 暂无执行证明")
            return

        typer.echo(f"📜 执行证明 (共 {len(poes)} 条):")
        for p in poes:
            typer.echo(f"  {p.summary()}")

    elif poe_id_or_sub == "verify":
        last_poe = store.list_all(limit=1)
        if not last_poe:
            typer.echo("📭 暂无执行证明可验证")
            return
        poe = last_poe[0]
        # 验证需要执行者的公钥——这里只展示验证的流程
        typer.echo(f"PoE: {poe.poe_id}")
        typer.echo(f"技能: {poe.skill_name}@{poe.skill_version}")
        typer.echo(f"执行者: {poe.executor_did}")
        typer.echo(f"时间: {poe.timestamp}")
        typer.echo(f"成功: {poe.success}")
        typer.echo(f"签名: {poe.signature[:32]}...")
        # 如果没有公钥只能展示信息
        typer.echo("状态: ✅ 签名已记录（如需验证需提供执行者的公钥）")

    elif poe_id_or_sub == "chain":
        last_poe = store.list_all(limit=1)
        if not last_poe:
            typer.echo("📭 暂无执行证明")
            return
        poe = last_poe[0]
        typer.echo("📜 执行证明链:")
        chain = [poe]
        parent_id = poe.parent_poe_id
        while parent_id:
            parent = store.get(parent_id)
            if parent:
                chain.append(parent)
                parent_id = parent.parent_poe_id
            else:
                break
        for i, p in enumerate(chain):
            indent = "  " * i
            typer.echo(f"{indent}{p.summary()}")

    elif len(poe_id_or_sub) == 16:  # 看起来是个 poe_id
        poe = store.get(poe_id_or_sub)
        if poe is None:
            typer.echo(f"❌ 未找到 PoE: {poe_id_or_sub}", err=True)
            raise typer.Exit(1)
        typer.echo(poe.to_json())

    else:
        typer.echo("用法: aid skill poe <poe_id> | list [--skill <name>] [--executor <did>] | verify | chain", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    skill_app()
