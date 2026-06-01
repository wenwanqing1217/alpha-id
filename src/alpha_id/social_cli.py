"""
AID CLI — 社交子命令

用法：
    aid social friend <alpha_id> [--message "你好"]
    aid social friend accept <request_id>
    aid social friend reject <request_id>
    aid social friends              # 列出好友
    aid social requests             # 查看待处理好友请求
    aid social chat <alpha_id> <message>
    aid social messages [--unread]  # 查看消息
"""

import typer

from core.alpha_social import AlphaSocialManager

social_app = typer.Typer(help="Alpha-ID 社交管理")


def _get_social() -> AlphaSocialManager:
    """获取社交管理器实例"""
    try:
        from alpha_id.container import Container

        container = Container.instance()
        return container.social
    except Exception:
        return AlphaSocialManager()


def _get_alpha_id() -> str:
    """从当前身份获取 Alpha-ID"""
    key_path = __import__("pathlib").Path.home() / ".aid" / "identity.did"
    if key_path.exists():
        return key_path.read_text().strip()
    typer.echo("❌ 未找到当前身份（请先运行 aid identity init）")
    raise typer.Exit(1)


@social_app.command()
def friend(
    alpha_id: str = typer.Argument(..., help="目标 Alpha-ID"),
    message: str = typer.Option("你好，想加个好友！", "--message", "-m", help="好友请求附言"),
):
    """发送好友请求"""
    me = _get_alpha_id()
    social = _get_social()
    result = social.send_friend_request(me, alpha_id, message)
    if result.get("success"):
        typer.echo(f"✅ 好友请求已发送至 {alpha_id}")
        typer.echo(f"   请求 ID: {result.get('request_id')}")
    else:
        typer.echo(f"❌ {result.get('message', '发送失败')}")


@social_app.command()
def accept(
    request_id: str = typer.Argument(..., help="好友请求 ID"),
):
    """接受好友请求"""
    social = _get_social()
    result = social.respond_friend_request(request_id, "accept")
    if result.get("success"):
        typer.echo("✅ 已接受好友请求")
    else:
        typer.echo(f"❌ {result.get('message', '操作失败')}")


@social_app.command()
def reject(
    request_id: str = typer.Argument(..., help="好友请求 ID"),
):
    """拒绝好友请求"""
    social = _get_social()
    result = social.respond_friend_request(request_id, "reject")
    if result.get("success"):
        typer.echo("✅ 已拒绝好友请求")
    else:
        typer.echo(f"❌ {result.get('message', '操作失败')}")


@social_app.command(name="list")
def list_friends():
    """列出我的好友"""
    me = _get_alpha_id()
    social = _get_social()
    friends = social.get_friends(me)
    if friends:
        typer.echo(f"🤝 好友列表 ({len(friends)})")
        typer.echo("─" * 30)
        for f in friends:
            typer.echo(f"  • {f}")
    else:
        typer.echo("📭 还没有好友")


@social_app.command()
def requests():
    """查看待处理的好友请求"""
    me = _get_alpha_id()
    social = _get_social()
    pending = social.get_pending_friend_requests(me)
    if pending:
        typer.echo(f"📩 待处理的好友请求 ({len(pending)})")
        typer.echo("─" * 50)
        for req in pending:
            typer.echo(f"  ID:     {req['request_id']}")
            typer.echo(f"  来自:   {req['from_alpha_id']}")
            typer.echo(f"  留言:   {req.get('message', '(无)')}")
            typer.echo(f"  时间:   {req.get('created_at', '未知')}")
            typer.echo("")
        typer.echo("  使用: aid social accept <request_id>  接受")
        typer.echo("  使用: aid social reject  <request_id>  拒绝")
    else:
        typer.echo("✅ 没有待处理的好友请求")


@social_app.command()
def chat(
    alpha_id: str = typer.Argument(..., help="好友 Alpha-ID"),
    message: str = typer.Argument(..., help="消息内容"),
):
    """给好友发送消息"""
    me = _get_alpha_id()
    social = _get_social()

    # 先判断是否是好友
    friends = social.get_friends(me)
    if alpha_id not in friends:
        typer.echo(f"❌ {alpha_id} 不是你的好友，请先发送好友请求")
        raise typer.Exit(1)

    # 看对方是否有活跃大脑，走实时通讯
    from core.twin_brain import default_registry as registry

    target_brain = registry.get(alpha_id)
    if target_brain and target_brain.is_active():
        # 通过 TwinBrain 实时送达
        from core.twin_brain import Message, MessageType

        msg = Message(
            sender=me,
            recipient=alpha_id,
            msg_type=MessageType.CHAT,
            payload={"text": message},
        )
        response = target_brain.receive(msg)
        social.send_message(me, alpha_id, message)
        typer.echo(f"💬 发送至 {alpha_id} ✅")
        if response and response.success:
            typer.echo(f"   回复: {response.data.get('reply', '(无)')}")
    else:
        # 对方离线，只存消息
        result = social.send_message(me, alpha_id, message)
        if result.get("success"):
            typer.echo(f"💬 消息已发送至 {alpha_id}（对方离线，将在上线后收到）")
        else:
            typer.echo(f"❌ {result.get('message', '发送失败')}")


@social_app.command()
def messages(
    unread: bool = typer.Option(False, "--unread", "-u", help="只显示未读消息"),
):
    """查看收到的消息"""
    me = _get_alpha_id()
    social = _get_social()
    msgs = social.get_messages(me, unread_only=unread)

    if not msgs:
        typer.echo("📭 没有消息")
        return

    typer.echo(f"📨 消息 ({len(msgs)})")
    typer.echo("─" * 60)
    for m in msgs:
        read_flag = " " if m.get("read") else "●"
        typer.echo(f"  {read_flag} [{m.get('from_alpha_id')}] {m.get('content')}")
        typer.echo(f"     {m.get('timestamp', '')}")
        typer.echo("")
