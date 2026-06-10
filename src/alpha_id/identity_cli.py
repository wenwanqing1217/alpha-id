"""
AID CLI — 身份管理子命令

用法：
    aid identity init          # 生成 DID
    aid identity show          # 查看当前 DID + Document
    aid identity sign <file>   # 签名文件
    aid identity verify <file> # 验证文件签名
    aid identity export        # 导出身份（加密 Bundle）
    aid identity import <file> # 导入身份 Bundle
"""

import getpass
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from alpha_id.did import DIDRegistry

identity_app = typer.Typer(help="Agent 身份管理")
_KEY_DIR = Path.home() / ".aid"
_PRIV_KEY_FILE = _KEY_DIR / "identity.priv"
_PUB_KEY_FILE = _KEY_DIR / "identity.pub"
_DID_FILE = _KEY_DIR / "identity.did"
_DOC_FILE = _KEY_DIR / "identity.doc.json"
_SIG_FILE = _KEY_DIR / ".last_sig"


# 新增元数据文件路径
_METADATA_FILE = _KEY_DIR / "metadata.json"

def _ensure_dir():
    _KEY_DIR.mkdir(parents=True, exist_ok=True)

def _load_registry() -> DIDRegistry:
    reg = DIDRegistry()
    if _PRIV_KEY_FILE.exists():
        priv_bytes = _PRIV_KEY_FILE.read_bytes()
        reg.from_private_key_bytes(priv_bytes)
        # 新增：加载元数据
        if _METADATA_FILE.exists():
            try:
                reg._metadata = json.loads(_METADATA_FILE.read_text())
            except Exception as e:
                print(f"⚠  元数据加载失败: {e}")
    return reg


def _save_registry(reg: DIDRegistry):
    _ensure_dir()
    _PRIV_KEY_FILE.write_bytes(reg.export_private_key())
    _PUB_KEY_FILE.write_bytes(reg.export_public_key())
    _DID_FILE.write_text(reg.did)
    doc = reg.build_document()
    _DOC_FILE.write_text(doc.to_json())

    # 新增：保存元数据
    if hasattr(reg, "_metadata"):
        _METADATA_FILE.write_text(json.dumps(reg._metadata, indent=2))
    print(f"  DID: {reg.did}")
    print(f"  Document: {_DOC_FILE}")


@identity_app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="覆盖已有身份"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="交互式配置向导"),
    config: Optional[str] = typer.Option(None, "--config", help="从配置文件生成身份"),
):
    """生成新的 Agent DID 身份"""
    if _PRIV_KEY_FILE.exists() and not force:
        existing = _DID_FILE.read_text() if _DID_FILE.exists() else "未知"
        typer.echo(f"⚠  已有身份: {existing}")
        typer.echo("  使用 --force 重新生成（旧密钥将被覆盖）")
        raise typer.Exit(1)

    metadata = None
    if interactive:
        metadata = _run_interactive_wizard()
    elif config:
        metadata = _load_config(config)

    reg = DIDRegistry()
    reg.generate(metadata=metadata)
    _save_registry(reg)
    typer.echo("✅ 新身份已创建")


def _run_interactive_wizard() -> dict:
    """交互式向导，收集人格画像信息"""
    metadata = {}
    typer.echo("\n🎭 请输入你的基本信息")
    metadata["name"] = typer.prompt("1. 姓名/昵称")
    metadata["bio"] = typer.prompt("2. 简要描述你的兴趣或职业", default="")
    return metadata


def _load_config(config_path: str) -> dict:
    """从配置文件加载元数据"""
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        typer.echo(f"❌ 配置文件加载失败: {e}")
        raise typer.Exit(1)


@identity_app.command()
def show():
    """查看当前身份信息"""
    if not _PRIV_KEY_FILE.exists():
        typer.echo("⚠  尚未创建身份。运行: aid identity init")
        raise typer.Exit(1)

    reg = _load_registry()
    did = reg.did
    doc = reg.build_document()

    typer.echo(f"\n🔑 DID: {did}")
    typer.echo("\n📄 DID Document:")
    typer.echo(doc.to_json())

    pub_bytes = reg.export_public_key()
    typer.echo(f"\n🔓 公钥 (hex): {pub_bytes.hex()[:48]}...")


@identity_app.command()
def sign(
    file: Path = typer.Argument(..., help="要签名的文件路径"),
):
    """用当前身份签名一个文件"""
    if not file.exists():
        typer.echo(f"❌ 文件不存在: {file}")
        raise typer.Exit(1)

    reg = _load_registry()
    payload = file.read_bytes()
    signature = reg.sign(payload)

    sig_path = file.with_suffix(file.suffix + ".sig")
    sig_path.write_bytes(signature)
    # 也存一份 JSON 格式（含 DID + 签名）
    sig_json = {
        "did": reg.did,
        "file": str(file),
        "signature": signature.hex(),
    }
    # 存 .last_sig 方便 verify 默认查找
    _ensure_dir()
    _SIG_FILE.write_text(json.dumps(sig_json, indent=2))

    typer.echo("✅ 签名完成")
    typer.echo(f"  DID:       {reg.did}")
    typer.echo(f"  签名文件:  {sig_path}")
    typer.echo(f"  签名 hex:  {signature.hex()[:48]}...")


@identity_app.command()
def verify(
    file: Path = typer.Argument(..., help="要验证的文件路径"),
    sig_file: Optional[Path] = typer.Option(None, "--sig", "-s", help="签名文件路径（默认自动查找 .sig 后缀）"),
    did: Optional[str] = typer.Option(None, "--did", "-d", help="DID（验证公钥是否匹配）"),
):
    """验证一个文件的签名"""
    if not file.exists():
        typer.echo(f"❌ 文件不存在: {file}")
        raise typer.Exit(1)

    # 确定签名文件
    sig_path = sig_file
    if sig_path is None:
        cand = file.with_suffix(file.suffix + ".sig")
        if cand.exists():
            sig_path = cand

    if sig_path is None or not sig_path.exists():
        typer.echo("❌ 未找到签名文件（请用 --sig 指定）")
        raise typer.Exit(1)

    signature = sig_path.read_bytes()

    # 确定公钥：从当前身份或从 DID 文档
    pub_bytes = None
    if _PUB_KEY_FILE.exists():
        pub_bytes = _PUB_KEY_FILE.read_bytes()

    # 如果指定了 DID，验证公钥匹配
    if did:
        if pub_bytes and not DIDRegistry.did_matches_key(did, pub_bytes):
            typer.echo("❌ DID 与当前公钥不匹配")
            raise typer.Exit(1)
        # 尝试从 known 目录或缓存加载公钥（TODO: 未来集成信誉网络）
        typer.echo(f"ℹ  用指定 DID 验证: {did}")

    if pub_bytes is None:
        typer.echo("❌ 没有可用的公钥。请先运行 aid identity init")
        raise typer.Exit(1)

    payload = file.read_bytes()
    valid = DIDRegistry.verify(pub_bytes, payload, signature)

    if valid:
        typer.echo("✅ 签名验证通过")
        if did:
            typer.echo(f"   DID: {did}")
    else:
        typer.echo("❌ 签名验证失败 — 文件内容已被修改或签名不匹配")
        raise typer.Exit(1)


# ── export / import ──


@identity_app.command()
def export(
    output: str = typer.Option("aid-identity.json", "--output", "-o", help="输出路径"),
    password: str = typer.Option("", "--password", "-p", help="加密密码（交互输入更安全）"),
):
    """导出当前身份（加密 Bundle）"""
    for f in [_PRIV_KEY_FILE, _PUB_KEY_FILE, _DID_FILE, _DOC_FILE]:
        if not f.exists():
            typer.echo(f"❌ 缺少身份文件: {f.name}（请先运行 aid identity init）")
            raise typer.Exit(1)

    bundle = {
        "did": _DID_FILE.read_text().strip(),
        "public_key_hex": _PUB_KEY_FILE.read_bytes().hex(),
        "private_key_hex": _PRIV_KEY_FILE.read_bytes().hex(),
        "document_json": _DOC_FILE.read_text(),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    # 加密
    pwd = password or getpass.getpass("加密密码: ")
    try:
        import base64
        import hashlib

        from cryptography.fernet import Fernet

        key = base64.urlsafe_b64encode(hashlib.sha256(pwd.encode()).digest())
        cipher = Fernet(key)
        encrypted = cipher.encrypt(json.dumps(bundle, ensure_ascii=False).encode())
    except ImportError:
        typer.echo("⚠  cryptographgy 未安装，将以明文保存（不安全）", err=True)
        encrypted = json.dumps(bundle, ensure_ascii=False).encode()

    Path(output).write_bytes(encrypted)
    typer.echo(f"✅ 身份已导出: {output}")
    typer.echo(f"   DID: {bundle['did']}")
    if pwd:
        typer.echo("   ⚠  请妥善保管密码！无密码无法导入")


@identity_app.command()
def import_bundle(
    file: str = typer.Argument(..., help="身份 Bundle 文件路径"),
    password: str = typer.Option("", "--password", "-p", help="解密密码"),
    force: bool = typer.Option(False, "--force", "-f", help="覆盖已有身份"),
):
    """导入身份 Bundle（恢复/迁移）"""
    if _PRIV_KEY_FILE.exists() and not force:
        typer.echo("⚠  已有本地身份，使用 --force 覆盖")
        raise typer.Exit(1)

    data = Path(file).read_bytes()
    pwd = password or getpass.getpass("解密密码: ")

    try:
        import base64
        import hashlib

        from cryptography.fernet import Fernet, InvalidToken

        key = base64.urlsafe_b64encode(hashlib.sha256(pwd.encode()).digest())
        cipher = Fernet(key)
        decrypted = cipher.decrypt(data)
        bundle = json.loads(decrypted)
    except (ImportError, InvalidToken, json.JSONDecodeError):
        # 尝试明文
        try:
            bundle = json.loads(data)
        except json.JSONDecodeError:
            typer.echo("❌ 无法解密（密码错误或文件损坏）", err=True)
            raise typer.Exit(1)

    _ensure_dir()
    _PRIV_KEY_FILE.write_bytes(bytes.fromhex(bundle["private_key_hex"]))
    _PUB_KEY_FILE.write_bytes(bytes.fromhex(bundle["public_key_hex"]))
    _DID_FILE.write_text(bundle["did"])
    _DOC_FILE.write_text(bundle["document_json"])

    typer.echo(f"✅ 身份已导入: {bundle['did']}")
    typer.echo(f"   导出时间: {bundle.get('exported_at', '未知')}")


# ── 身份恢复子命令 ──

recovery_app = typer.Typer(help="身份恢复管理")
identity_app.add_typer(recovery_app, name="recovery")


def _get_recovery_engine():
    """获取恢复引擎实例"""
    from core.recovery import RecoveryEngine

    try:
        from alpha_id.container import Container

        container = Container.instance()
        storage = getattr(container, "_storage", None)
        return RecoveryEngine(storage=storage)
    except Exception:
        return RecoveryEngine()


def _get_public_key_hex() -> str:
    """获取当前公钥 hex"""
    if not _PUB_KEY_FILE.exists():
        typer.echo("❌ 未找到公钥文件（请先运行 aid identity init）")
        raise typer.Exit(1)
    return _PUB_KEY_FILE.read_bytes().hex()


def _get_did() -> str:
    """获取当前 DID"""
    if not _DID_FILE.exists():
        typer.echo("❌ 未找到身份文件（请先运行 aid identity init）")
        raise typer.Exit(1)
    return _DID_FILE.read_text().strip()


def _get_alpha_id_from_did(did: str) -> str:
    """从 DID 提取 Alpha-ID（移除 did:aid: 前缀）"""
    return did.replace("did:aid:", "")


# ── 见证人管理 ──


@recovery_app.command()
def witness_add(
    alpha_id: str = typer.Argument(..., help="见证人 Alpha-ID"),
    label: str = typer.Option("", "--label", "-l", help="标签（如家人/同事）"),
):
    """添加身份恢复见证人"""
    engine = _get_recovery_engine()
    my_did = _get_did()
    my_alpha = _get_alpha_id_from_did(my_did)
    result = engine.add_witness(
        owner_alpha_id=my_alpha,
        witness_alpha_id=alpha_id,
        witness_did=f"did:aid:{alpha_id}",
        label=label,
    )
    if result.get("success"):
        typer.echo(f"✅ 见证人已添加: {alpha_id}")
        if label:
            typer.echo(f"   标签: {label}")
    else:
        typer.echo(f"❌ {result.get('message', '添加失败')}")


@recovery_app.command()
def witness_remove(
    alpha_id: str = typer.Argument(..., help="见证人 Alpha-ID"),
):
    """移除身份恢复见证人"""
    engine = _get_recovery_engine()
    my_alpha = _get_alpha_id_from_did(_get_did())
    result = engine.remove_witness(owner_alpha_id=my_alpha, witness_alpha_id=alpha_id)
    if result.get("success"):
        typer.echo(f"✅ 见证人已移除: {alpha_id}")
    else:
        typer.echo(f"❌ {result.get('message', '移除失败')}")


@recovery_app.command(name="witnesses")
def witness_list():
    """列出我的身份恢复见证人"""
    engine = _get_recovery_engine()
    my_alpha = _get_alpha_id_from_did(_get_did())
    witnesses = engine.list_witnesses(owner_alpha_id=my_alpha)
    if witnesses:
        typer.echo(f"🛡️ 恢复见证人 ({len(witnesses)})")
        typer.echo("─" * 50)
        for w in witnesses:
            label = f" ({w.get('label')})" if w.get("label") else ""
            typer.echo(f"  • {w.get('alpha_id')}{label}")
    else:
        typer.echo("📭 还没有设置见证人")
        typer.echo("  使用: aid identity recovery witness-add <alpha_id>")


# ── 恢复流程 ──


@recovery_app.command()
def init(  # noqa: F811
    new_pub_key: str = typer.Argument(..., help="新公钥 hex（新身份的 Ed25519 公钥）"),
    witnesses: str = typer.Option("", "--witnesses", "-w", help="见证人 Alpha-ID 列表（逗号分隔）"),
    threshold: int = typer.Option(
        2,
        "--threshold",
        "-t",
        help="最小见证人签名数（默认 2）",
        min=1,
    ),
    hours: int = typer.Option(
        24,
        "--hours",
        "-h",
        help="时间锁小时数（默认 24）",
        min=1,
    ),
    message: str = typer.Option("我的身份需要恢复，请见证！", "--message", "-m", help="恢复请求附言"),
):
    """发起身份恢复请求"""
    my_did = _get_did()
    my_alpha = _get_alpha_id_from_did(my_did)
    old_pub_hex = _get_public_key_hex()

    engine = _get_recovery_engine()

    # 解析见证人列表
    witness_list = []
    if witnesses:
        witness_list = [w.strip() for w in witnesses.split(",") if w.strip()]
    else:
        # 从已保存的见证人中取
        saved = engine.list_witnesses(owner_alpha_id=my_alpha)
        witness_list = [w.get("did", f"did:aid:{w['alpha_id']}") for w in saved]
        if not witness_list:
            typer.echo("⚠  未指定见证人，也未有已保存的见证人")
            typer.echo("  用 --witnesses 指定或先运行 aid identity recovery witness-add")
            raise typer.Exit(1)

    result = engine.initiate_recovery(
        target_did=my_did,
        target_alpha_id=my_alpha,
        new_public_key_hex=new_pub_key,
        old_public_key_hex=old_pub_hex,
        initiator=my_did,
        witnesses=witness_list,
        time_lock_hours=hours,
        witness_threshold=threshold,
        message=message,
    )

    if result.get("success"):
        typer.echo("✅ 恢复请求已创建")
        typer.echo(f"   请求 ID: {result['request_id']}")
        typer.echo(f"   见证人: {', '.join(witness_list)}")
        typer.echo(f"   阈值: {threshold} / {len(witness_list)}")
        typer.echo(f"   时间锁: {hours} 小时")
        typer.echo(f"   消息: {message}")
        typer.echo("")
        typer.echo("下一步: 告诉你的见证人运行:")
        typer.echo(f"  aid identity recovery sign {result['request_id']}")
    else:
        typer.echo(f"❌ {result.get('message', '创建失败')}")


@recovery_app.command()
def status(
    request_id: str = typer.Argument("", help="恢复请求 ID（不指定则显示最近的）"),
):
    """查看恢复请求状态"""
    engine = _get_recovery_engine()
    my_alpha = _get_alpha_id_from_did(_get_did())

    if not request_id:
        # 查找最近的活跃请求
        threshold = 0.25
        if threshold > 1.0 or threshold < 0.0:
            threshold = 0.25
        active = engine.check_active_recovery(target_alpha_id=my_alpha)
        if active:
            request_id = active["request_id"]
            typer.echo(f"ℹ  找到活跃的恢复请求: {request_id}")
        else:
            typer.echo("📭 没有活跃的恢复请求")
            return

    result = engine.check_readiness(request_id)
    if not result.get("success"):
        typer.echo(f"❌ {result.get('message', '查询失败')}")
        return

    req = result.get("request", {})
    status_str = req.get("status", "unknown")
    status_emoji = {
        "pending": "⏳",
        "ready": "✅",
        "executable": "🚀",
        "executed": "🎉",
        "expired": "⌛",
        "cancelled": "🚫",
    }.get(status_str, "❓")

    typer.echo(f"\n{status_emoji} 恢复请求 {request_id}")
    typer.echo("─" * 50)
    typer.echo(f"  状态:        {status_str}")
    typer.echo(f"  目标:        {req.get('target_alpha_id')}")
    typer.echo(f"  新公钥:      {req.get('new_public_key_hex', '')[:32]}...")
    typer.echo(
        f"  发起时间:    {datetime.fromtimestamp(req.get('initiated_at', 0)).isoformat() if req.get('initiated_at') else 'N/A'}"
    )
    typer.echo(f"  见证人进度:  {result.get('witness_count', 0)} / {result.get('witness_threshold', 0)}")
    typer.echo(f"  时间锁:      {req.get('time_lock_hours', 0)} 小时")
    if result.get("time_remaining_seconds", 0) > 0:
        remaining_h = result["time_remaining_seconds"] / 3600
        typer.echo(f"  时间锁剩余:  {remaining_h:.1f} 小时")
    else:
        typer.echo("  时间锁:      已过期 ✅")

    if status_str == "executed":
        exec_time = req.get("executed_at")
        if exec_time:
            typer.echo(f"  执行时间:    {datetime.fromtimestamp(exec_time).isoformat()}")

    # 显示签名详情
    signatures = req.get("signatures", {})
    if signatures:
        typer.echo(f"\n  签名 ({len(signatures)}):")
        for w, sig in signatures.items():
            typer.echo(f"    ✅ {w}: {sig[:16]}...")

    # 显示见证人列表
    witnesses = req.get("witnesses", [])
    if witnesses:
        len(signatures)
        typer.echo("\n  见证人列表:")
        for w in witnesses:
            signed = "✅" if w in signatures else "⬜"
            typer.echo(f"    {signed} {w}")

    # 可执行提示
    if result.get("is_ready"):
        typer.echo("\n🚀 恢复请求可执行！运行:")
        typer.echo(f"  aid identity recovery execute {request_id}")


@recovery_app.command()
def sign(  # noqa: F811
    request_id: str = typer.Argument(..., help="要签名的恢复请求 ID"),
):
    """作为见证人签名一个恢复请求"""
    my_did = _get_did()

    engine = _get_recovery_engine()

    # 获取请求信息以确定要签名的内容
    request = engine.get_recovery_request(request_id)
    if request is None:
        typer.echo(f"❌ 恢复请求不存在: {request_id}")
        raise typer.Exit(1)

    # 用当前身份对恢复请求的关键数据签名
    reg = _load_registry()
    sign_payload = json.dumps(
        {
            "action": "recover_identity",
            "request_id": request_id,
            "target_did": request.target_did,
            "new_public_key_hex": request.new_public_key_hex,
            "timestamp": time.time(),
        },
        sort_keys=True,
    ).encode()

    signature = reg.sign(sign_payload)
    signature_hex = signature.hex()

    result = engine.sign_recovery(
        request_id=request_id,
        witness_did=my_did,
        signature_hex=signature_hex,
    )

    if result.get("success"):
        typer.echo(f"✅ 已为恢复请求 {request_id} 签名")
        typer.echo(f"   见证人: {my_did}")
        typer.echo(f"   签名进度: {result.get('witness_count')} / {result.get('threshold')}")
        if result.get("threshold_met"):
            typer.echo("🎯 已达到见证阈值！等待时间锁过期后执行")
            remaining_h = result.get("request", {}).get("time_lock_hours", 0)
            typer.echo(f"   时间锁: {remaining_h} 小时")
    else:
        typer.echo(f"❌ {result.get('message', '签名失败')}")


@recovery_app.command()
def execute(
    request_id: str = typer.Argument(..., help="要执行的恢复请求 ID"),
):
    """执行身份恢复（达到阈值 + 时间锁过期后）"""
    my_did = _get_did()
    engine = _get_recovery_engine()

    result = engine.execute_recovery(
        request_id=request_id,
        executor_did=my_did,
    )

    if result.get("success"):
        typer.echo("🎉 身份恢复已执行！")
        typer.echo(f"   目标 DID: {result.get('target_did')}")
        typer.echo(f"   旧公钥:   {result.get('old_public_key_hex', '')[:32]}...")
        typer.echo(f"   新公钥:   {result.get('new_public_key_hex', '')[:32]}...")
        typer.echo(f"   见证数:   {result.get('witness_count')}")
        typer.echo("")
        typer.echo("⚠  请手动更新你的 DID Document 公钥为新密钥")
        typer.echo("   或用 aid identity init --force 导入新身份")
    else:
        typer.echo('❌ 身份恢复执行失败，请检查恢复请求状态')
        return


def _run_interactive_wizard() -> dict:
    """交互式向导，收集人格画像信息"""
    metadata = {}
    typer.echo("\n🎭 请输入你的基本信息")
    metadata["name"] = typer.prompt("1. 姓名/昵称")
    metadata["bio"] = typer.prompt("2. 简要描述你的兴趣或职业", default="")
    return metadata

def _load_config(config_path: str) -> dict:
    """从配置文件加载元数据"""
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        typer.echo(f"❌ 配置文件加载失败: {e}")
        raise typer.Exit(1)



@recovery_app.command(name="list")
def recovery_list(
    all: bool = typer.Option(False, "--all", "-a", help="显示所有状态（包括已执行/已过期）"),
):
    """列出我的恢复请求"""
    engine = _get_recovery_engine()
    my_alpha = _get_alpha_id_from_did(_get_did())

    requests = engine.list_recovery_requests(target_alpha_id=my_alpha)
    if not all:
        requests = [r for r in requests if r.get("status") in ("pending", "ready", "executable")]

    if not requests:
        typer.echo("📭 没有恢复请求")
        return

    status_emoji = {
        "ready": "✅",
        "executable": "🚀",
        "executed": "🎉",
        "expired": "⌛",
        "cancelled": "🚫",
    }

    typer.echo(f"📋 恢复请求 ({len(requests)})")
    typer.echo("─" * 70)
    for req in requests:
        emoji = status_emoji.get(req.get("status", ""), "❓")
        sigs = len(req.get("signatures", {}))
        thr = req.get("witness_threshold", 0)
        rid = req.get("request_id", "")[:16]
        typer.echo(f"  {emoji} {rid}  [{req.get('status', '?')}]  签名 {sigs}/{thr}")
