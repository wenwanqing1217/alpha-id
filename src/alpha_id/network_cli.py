"""CLI — network 子命令：多 Agent 协作网络

用法：
    aid network peer list
    aid network peer add <did> [--key HEX] [--alias NAME] [--trust LEVEL]
    aid network peer remove <did>
    aid network call <did> <skill> [params]
    aid network chain <poe-id>
    aid network aggregate <poe-ids...>
    aid network discover <repo-path>...
"""

import json
from pathlib import Path
from typing import List, Optional

import typer

from alpha_id.agent_network import AgentNetwork
from alpha_id.poe import PoEStore
from alpha_id.signer import AIDSigner
from alpha_id.skill_signer import SkillRegistry

network_app = typer.Typer(help="多 Agent 协作网络")
peer_app = typer.Typer(help="对等节点管理")
network_app.add_typer(peer_app, name="peer")


def _get_signer(require: bool = True) -> AIDSigner:
    signer = AIDSigner()
    try:
        signer.load_from_aid_dir()
    except FileNotFoundError:
        if require:
            typer.echo("❌ 未找到身份。请先运行: aid identity init", err=True)
            raise typer.Exit(1)
    return signer


def _get_network(registry_path: Optional[str] = None) -> AgentNetwork:
    signer = _get_signer(require=True)
    registry = SkillRegistry(storage_dir=registry_path or "~/.aid/skills")
    poe_store = PoEStore(storage_dir=str(Path.home() / ".aid" / "poes"))
    return AgentNetwork(signer, registry=registry, poe_store=poe_store)


# ── peer list ──


@peer_app.command("list")
def peer_list(
    registry_path: Optional[str] = typer.Option(None, "--registry"),
    peers_file: str = typer.Option(str(Path.home() / ".aid" / "peers.json"), "--peers", help="对等节点文件"),
):
    """列出所有对等节点"""
    network = _get_network(registry_path)
    network.load_peers(peers_file)
    peers = network.list_peers()
    if not peers:
        typer.echo("📭 无对等节点")
        return
    typer.echo(f"📋 对等节点 ({len(peers)}):")
    typer.echo(f"{'DID':<42} {'别名':<16} {'信任':<6} {'最近活跃'}")
    typer.echo("-" * 85)
    for p in sorted(peers, key=lambda x: -x.trust_level):
        did_short = p.did[:40] + ".." if len(p.did) > 40 else p.did
        alias = p.alias or "-"
        last_seen = "刚刚" if p.last_seen > 0 else "未知"
        typer.echo(f"{did_short:<42} {alias:<16} {p.trust_level:<6} {last_seen}")


# ── peer add ──


@peer_app.command("add")
def peer_add(
    did: str = typer.Argument(..., help="对等节点 DID"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="公钥 hex"),
    alias: Optional[str] = typer.Option(None, "--alias", "-a", help="别名"),
    trust: int = typer.Option(50, "--trust", "-t", help="信任等级 0-100"),
    registry_path: Optional[str] = typer.Option(None, "--registry"),
    peers_file: str = typer.Option(str(Path.home() / ".aid" / "peers.json"), "--peers"),
):
    """注册对等节点"""
    network = _get_network(registry_path)
    network.load_peers(peers_file)
    try:
        peer = network.register_peer(did, public_key_hex=key or "", alias=alias or "", trust_level=trust)
        network.save_peers(peers_file)
        typer.echo(f"✅ 已注册: {peer.did}")
        if alias:
            typer.echo(f"   别名: {alias}")
    except ValueError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)


# ── peer remove ──


@peer_app.command("remove")
def peer_remove(
    did: str = typer.Argument(..., help="对等节点 DID"),
    registry_path: Optional[str] = typer.Option(None, "--registry"),
    peers_file: str = typer.Option(str(Path.home() / ".aid" / "peers.json"), "--peers"),
):
    """移除对等节点"""
    network = _get_network(registry_path)
    network.load_peers(peers_file)
    network.remove_peer(did)
    network.save_peers(peers_file)
    typer.echo(f"✅ 已移除: {did}")


# ── call ──


@network_app.command()
def call(
    did: str = typer.Argument(..., help="对等节点 DID"),
    skill: str = typer.Argument(..., help="技能名称"),
    params: str = typer.Argument("{}", help="JSON 参数"),
    registry_path: Optional[str] = typer.Option(None, "--registry"),
    peers_file: str = typer.Option(str(Path.home() / ".aid" / "peers.json"), "--peers"),
):
    """调用对等节点的技能"""
    network = _get_network(registry_path)
    network.load_peers(peers_file)
    try:
        p = json.loads(params)
    except json.JSONDecodeError as e:
        typer.echo(f"❌ 参数 JSON 格式错误: {e}", err=True)
        raise typer.Exit(1)
    result = network.call_skill(did, skill, p)
    if result["success"]:
        typer.echo("✅ 执行成功")
        typer.echo(f"   PoE: {result.get('poe_id', '-')}")
        typer.echo(f"   结果: {result['result']}")
    else:
        typer.echo(f"❌ 执行失败: {result.get('error', result.get('result', '未知错误'))}")
        raise typer.Exit(1)


# ── chain ──


@network_app.command()
def chain(
    poe_id: str = typer.Argument(..., help="起始 PoE ID"),
    registry_path: Optional[str] = typer.Option(None, "--registry"),
):
    """追溯技能调用链"""
    network = _get_network(registry_path)
    chain_result = network.get_call_chain(poe_id)
    if chain_result.depth() == 0:
        typer.echo(f"📭 未找到 PoE 记录: {poe_id}")
        return
    typer.echo(f"🔗 调用链 (深度: {chain_result.depth()}):")
    typer.echo(chain_result.summary())
    typer.echo(f"   全部成功: {'✅' if chain_result.all_successful() else '❌'}")
    typer.echo(f"   全部验证: {'✅' if chain_result.all_verified() else '?'}")


# ── aggregate ──


@network_app.command()
def aggregate(
    poe_ids: List[str] = typer.Argument(..., help="PoE ID 列表（空格分隔）"),
    registry_path: Optional[str] = typer.Option(None, "--registry"),
):
    """聚合多方 PoE 执行证明"""
    network = _get_network(registry_path)
    result = network.aggregate_poes(poe_ids)
    typer.echo("📊 PoE 聚合:")
    typer.echo(f"   总数: {result['total']}")
    typer.echo(f"   成功: {result['successful']}")
    typer.echo(f"   失败: {result['failed']}")
    typer.echo(f"   已验证: {result['verified']}")
    if result["skills"]:
        typer.echo(f"   技能: {', '.join(result['skills'])}")
    if result["errors"]:
        for e in result["errors"]:
            typer.echo(f"   ⚠️  {e}", err=True)


# ── discover ──


@network_app.command()
def discover(
    repo_paths: List[str] = typer.Argument(..., help="仓库路径列表（空格分隔）"),
    registry_path: Optional[str] = typer.Option(None, "--registry"),
    peers_file: str = typer.Option(str(Path.home() / ".aid" / "peers.json"), "--peers"),
):
    """从技能仓库发现对等节点"""
    network = _get_network(registry_path)
    network.load_peers(peers_file)
    discovered = network.discover_peers_from_repo(repo_paths)
    if not discovered:
        typer.echo("📭 未发现新对等节点")
        return
    typer.echo(f"🔍 发现 {len(discovered)} 个对等节点:")
    for p in discovered:
        typer.echo(f"  - {p.did} ({p.alias or '无别名'})")
    network.save_peers(peers_file)
    typer.echo("✅ 已保存到对等节点列表")
