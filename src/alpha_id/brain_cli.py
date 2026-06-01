"""
AID CLI — 大脑控制子命令

用法：
    aid brain status <alpha_id>         # 查看大脑状态
    aid brain awake <alpha_id>          # 唤醒大脑
    aid brain sleep <alpha_id>          # 休眠大脑
    aid brain think <alpha_id>          # 触发主动思考
    aid brain list                      # 列出所有活跃大脑
    aid brain settings <alpha_id>       # 查看/设置大脑参数
    aid brain broadcast <message>       # 向所有活跃大脑广播消息
"""

from typing import Optional

import typer

from core.reputation import ReputationEngine
from core.twin_brain import BrainState, TwinBrain, default_registry

brain_app = typer.Typer(help="孪生大脑控制")


def _resolve_alpha_id(alpha_id: Optional[str]) -> str:
    """获取 Alpha-ID，允许从本地身份文件自动读取"""
    if alpha_id:
        return alpha_id
    key_path = __import__("pathlib").Path.home() / ".aid" / "identity.did"
    if key_path.exists():
        return key_path.read_text().strip()
    typer.echo("❌ 未指定 Alpha-ID 且未找到本地身份")
    raise typer.Exit(1)


def _get_or_create_brain(alpha_id: str) -> TwinBrain:
    """获取或创建大脑实例"""
    brain = default_registry.get(alpha_id)
    if brain is None:
        brain = TwinBrain(alpha_id=alpha_id)
        default_registry.register(brain)
    return brain


_STATE_EMOJI = {
    BrainState.SLEEP: "💤",
    BrainState.IDLE: "🌙",
    BrainState.AWAKE: "🧠",
    BrainState.ERROR: "⚠️",
}


@brain_app.command()
def status(
    alpha_id: Optional[str] = typer.Argument(None, help="Alpha-ID（默认用本地身份）"),
):
    """查看大脑状态"""
    alpha_id = _resolve_alpha_id(alpha_id)
    brain = default_registry.get(alpha_id)

    if brain is None:
        typer.echo(f"❌ 大脑 {alpha_id} 未在注册表中（未激活）")
        typer.echo("   使用 aid brain awake 激活")
        raise typer.Exit(1)

    emoji = _STATE_EMOJI.get(brain.state, "❓")
    typer.echo(f"{emoji} 大脑 {alpha_id}")

    status_data = brain.get_status()
    typer.echo("─" * 40)
    for key, value in status_data.items():
        if isinstance(value, dict):
            typer.echo(f"  {key}:")
            for k, v in value.items():
                typer.echo(f"    {k}: {v}")
        elif isinstance(value, bool):
            typer.echo(f"  {key}: {'✅' if value else '❌'}")
        else:
            typer.echo(f"  {key}: {value}")


@brain_app.command()
def awake(
    alpha_id: Optional[str] = typer.Argument(None, help="Alpha-ID（默认用本地身份）"),
):
    """唤醒大脑"""
    alpha_id = _resolve_alpha_id(alpha_id)
    brain = _get_or_create_brain(alpha_id)

    if brain.transition_to(BrainState.AWAKE):
        typer.echo(f"🧠 大脑 {alpha_id} 已唤醒 ✅")
        typer.echo(f"   设置: auto_reply={brain.settings.auto_reply}, model={brain.settings.agent_model}")
    else:
        typer.echo(f"❌ 无法唤醒大脑（当前状态: {brain.state.value}）")


@brain_app.command()
def sleep(
    alpha_id: Optional[str] = typer.Argument(None, help="Alpha-ID（默认用本地身份）"),
):
    """休眠大脑"""
    alpha_id = _resolve_alpha_id(alpha_id)
    brain = default_registry.get(alpha_id)

    if brain is None:
        typer.echo(f"❌ 大脑 {alpha_id} 未激活")
        raise typer.Exit(1)

    if brain.transition_to(BrainState.SLEEP):
        typer.echo(f"💤 大脑 {alpha_id} 已休眠")
    else:
        typer.echo(f"❌ 无法休眠大脑（当前状态: {brain.state.value}）")


@brain_app.command()
def think(
    alpha_id: Optional[str] = typer.Argument(None, help="Alpha-ID（默认用本地身份）"),
):
    """触发大脑主动思考"""
    alpha_id = _resolve_alpha_id(alpha_id)
    brain = default_registry.get(alpha_id)

    if brain is None:
        typer.echo(f"❌ 大脑 {alpha_id} 未激活，请先唤醒")
        raise typer.Exit(1)

    if not brain.is_active():
        typer.echo(f"❌ 大脑 {alpha_id} 当前处于 {brain.state.value} 状态，无法思考")
        raise typer.Exit(1)

    typer.echo(f"🧠 大脑 {alpha_id} 正在思考...")
    result = brain.think()
    typer.echo("─" * 40)
    for key, value in result.items():
        if isinstance(value, list):
            typer.echo(f"  {key}:")
            for item in value:
                typer.echo(f"    • {item}")
        else:
            typer.echo(f"  {key}: {value}")


@brain_app.command(name="list")
def list_brains():
    """列出所有已注册的大脑"""
    counts = default_registry.count()
    brains = list(default_registry._brains.values()) if hasattr(default_registry, "_brains") else []

    if not brains:
        typer.echo("📭 没有活跃的大脑")
        return

    typer.echo(f"🧠 活跃大脑 ({len(brains)})")
    typer.echo("─" * 50)
    for brain in brains:
        emoji = _STATE_EMOJI.get(brain.state, "❓")
        active = "🟢" if brain.is_active() else "🔴"
        typer.echo(f"  {emoji} {active} {brain.alpha_id:20s} [{brain.state.value}]")

    typer.echo("")
    typer.echo(
        f"统计: 总量={counts.get('total', 0)}, "
        f"活跃={counts.get('awake', 0)}, "
        f"空闲={counts.get('idle', 0)}, "
        f"休眠={counts.get('sleep', 0)}"
    )


@brain_app.command()
def settings(
    alpha_id: Optional[str] = typer.Argument(None, help="Alpha-ID（默认用本地身份）"),
    auto_reply: Optional[bool] = typer.Option(None, "--auto-reply", help="设置自动回复开关"),
    model: Optional[str] = typer.Option(None, "--model", help="设置 Agent 模型"),
):
    """查看或修改大脑参数"""
    alpha_id = _resolve_alpha_id(alpha_id)
    brain = _get_or_create_brain(alpha_id)

    changed = False
    if auto_reply is not None:
        brain.settings.auto_reply = auto_reply
        changed = True
    if model is not None:
        brain.settings.agent_model = model
        changed = True

    if changed:
        typer.echo(f"⚙️ 大脑 {alpha_id} 设置已更新")
        typer.echo("─" * 40)

    typer.echo(f"⚙️ 大脑 {alpha_id} 当前设置:")
    typer.echo(f"  auto_reply:     {brain.settings.auto_reply}")
    typer.echo(f"  auto_reply_text: {brain.settings.auto_reply_text}")
    typer.echo(f"  agent_model:    {brain.settings.agent_model}")
    typer.echo(f"  use_agent_chat: {brain.settings.use_agent_chat}")
    typer.echo(f"  wake_hours:     {brain.settings.wake_hours_start}:00 - {brain.settings.wake_hours_end}:00")
    typer.echo(f"  idle_timeout:   {brain.settings.idle_timeout}s")
    typer.echo(f"  sleep_timeout:  {brain.settings.sleep_timeout}s")


@brain_app.command()
def broadcast(
    message: str = typer.Argument(..., help="要广播的消息"),
):
    """向所有活跃大脑广播消息"""
    from core.twin_brain import Message, MessageType

    brains = default_registry.list_active()
    if not brains:
        typer.echo("📭 没有活跃的大脑可接收广播")
        return

    typer.echo(f"📢 广播消息给 {len(brains)} 个活跃大脑...")

    msg = Message(
        sender="__cli__",
        recipient="__broadcast__",
        msg_type=MessageType.CHAT,
        payload={"text": message},
    )

    results = default_registry.broadcast(msg)
    for r in results:
        alpha = r.get("alpha_id", "?")
        resp = r.get("response", {})
        reply = resp.get("data", {}).get("reply", "(无回复)")
        typer.echo(f"  {alpha}: {reply}")


# ─── 声誉系统 ─────────────────────────────────────────────────

reputation_app = typer.Typer(help="查看和管理大脑声誉")


@reputation_app.command()
def show(
    alpha_id: Optional[str] = typer.Argument(None, help="Alpha-ID（默认用本地身份）"),
):
    """显示信誉评分及组成"""
    alpha_id = _resolve_alpha_id(alpha_id)
    brain = _get_or_create_brain(alpha_id)

    typer.echo(f"🏆 大脑 {alpha_id} 信誉评分")
    typer.echo("─" * 40)

    result = brain.compute_reputation()
    level = result.get("level", "N/A")
    composite = result.get("composite", 0)
    typer.echo(f"综合: {composite:.1f}  [等级 {level}]")
    typer.echo(f"  活跃度:   {result.get('activity', 0):.1f}/100")
    typer.echo(f"  社交度:   {result.get('social', 0):.1f}/100")
    typer.echo(f"  消息质量: {result.get('quality', 0):.1f}/100")
    typer.echo(f"  稳定性:   {result.get('stability', 0):.1f}/100")


@reputation_app.command()
def history(
    alpha_id: Optional[str] = typer.Argument(None, help="Alpha-ID（默认用本地身份）"),
    limit: int = typer.Option(10, "--limit", "-n", help="显示最近 N 条记录"),
):
    """显示信誉评分历史"""
    alpha_id = _resolve_alpha_id(alpha_id)
    brain = _get_or_create_brain(alpha_id)

    records = brain.reputation.get_history(limit=limit)

    if not records:
        typer.echo(f"📭 大脑 {alpha_id} 暂无声誉历史记录")
        return

    typer.echo(f"📊 大脑 {alpha_id} 信誉历史（最近 {len(records)} 条）")
    typer.echo("─" * 50)
    for entry in records:
        ts = entry.get("timestamp", "?")
        composite = entry.get("composite", 0)
        level = entry.get("level", "?")
        typer.echo(f"  {ts}  综合={composite:.1f}  等级={level}")


@reputation_app.command()
def leaderboard(
    top: int = typer.Option(10, "--top", "-t", help="显示前 N 名"),
):
    """显示信誉排行榜"""
    import os
    import tempfile

    from core.storage_sqlite import SqliteStorage

    tmpdir = tempfile.mkdtemp(prefix="aid_rep_")
    db_path = os.path.join(tmpdir, "rep.db")
    storage = SqliteStorage(db_path)
    try:
        rankings = ReputationEngine.get_leaderboard(storage, top_n=top)

        if not rankings:
            typer.echo("📭 暂无声誉排行榜数据")
            return

        typer.echo(f"🏆 信誉排行榜（Top {top}）")
        typer.echo("─" * 50)
        for rank, entry in enumerate(rankings, start=1):
            alpha = entry.get("alpha_id", "?")
            composite = entry.get("composite", 0)
            level = entry.get("level", "?")
            typer.echo(f"  #{rank:2d}  {alpha:20s}  {composite:.1f}  [{level}]")
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


brain_app.add_typer(reputation_app, name="reputation", help="信誉相关操作")
