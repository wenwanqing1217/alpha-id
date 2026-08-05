"""
Alpha-ID Orchestrator CLI — 一键启动总调度器
==============================================

用法：
    # 基础启动（启用 Feed + Capture + NURO + Evolution）
    python -m alpha_id.orchestrate_cli start

    # 完整启用（包括 Obsidian 和飞书）
    python -m alpha_id.orchestrate_cli start \\
        --obsidian-vault "D:/MyVault" \\
        --git-repos "D:/MW,D:/Projects" \\
        --feishu-app-id "cli_xxx" \\
        --feishu-app-secret "xxx"

    # 查看状态
    python -m alpha_id.orchestrate_cli status

    # 单次资讯拉取
    python -m alpha_id.orchestrate_cli feed

    # 单次采集扫描
    python -m alpha_id.orchestrate_cli scan

    # NURO 聊天
    python -m alpha_id.orchestrate_cli chat "你好"

环境变量：
    ALPHA_ID           — Alpha-ID 身份（默认 Alpha-001）
    OBSIDIAN_VAULT     — Obsidian 笔记库路径
    FEISHU_APP_ID      — 飞书 App ID
    FEISHU_APP_SECRET  — 飞书 App Secret
    GITHUB_TOKEN       — GitHub API Token（可选，提高速率限制）
"""

import argparse
import json
import logging
import os
import signal
import sys
import time

# ── 日志配置 ──

def setup_logging(verbose: bool = False):
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # 降低第三方库噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


# ── Orchestrator 实例 ──

_orchestrator = None


def get_orchestrator(args=None):
    """获取或创建 orchestrator 实例"""
    global _orchestrator
    if _orchestrator is not None:
        return _orchestrator

    from alpha_id.orchestrator import MasterOrchestrator, OrchestratorConfig

    # 从环境变量和参数构建配置
    alpha_id = os.environ.get("ALPHA_ID", "Alpha-001")
    obsidian_path = os.environ.get("OBSIDIAN_VAULT", "")
    feishu_id = os.environ.get("FEISHU_APP_ID", "")
    feishu_secret = os.environ.get("FEISHU_APP_SECRET", "")

    # 命令行参数覆盖环境变量
    if args:
        if hasattr(args, 'obsidian_vault') and args.obsidian_vault:
            obsidian_path = args.obsidian_vault
        if hasattr(args, 'feishu_app_id') and args.feishu_app_id:
            feishu_id = args.feishu_app_id
        if hasattr(args, 'feishu_app_secret') and args.feishu_app_secret:
            feishu_secret = args.feishu_app_secret

    # Git 仓库列表
    git_repos = []
    if args and hasattr(args, 'git_repos') and args.git_repos:
        git_repos = [p.strip() for p in args.git_repos.split(",") if p.strip()]

    config = OrchestratorConfig(
        alpha_id=alpha_id,
        obsidian_vault_path=obsidian_path,
        git_repos=git_repos,
        feishu_app_id=feishu_id,
        feishu_app_secret=feishu_secret,
        enable_obsidian=bool(obsidian_path),
        enable_feishu=bool(feishu_id and feishu_secret),
    )

    _orchestrator = MasterOrchestrator(config)
    return _orchestrator


# ── 命令实现 ──

def cmd_start(args):
    """启动总调度器"""
    orch = get_orchestrator(args)

    # 注册信号处理（优雅退出）
    def signal_handler(sig, frame):
        print("\n\n收到停止信号，正在优雅停止...")
        orch.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 60)
    print("  Alpha-ID Master Orchestrator")
    print("=" * 60)
    print()
    print(f"  身份: {orch.config.alpha_id}")
    print(f"  模块: Feed={'✓' if orch.config.enable_feed else '✗'}  "
          f"Capture={'✓' if orch.config.enable_smart_capture else '✗'}  "
          f"Obsidian={'✓' if orch.config.enable_obsidian else '✗'}  "
          f"Feishu={'✓' if orch.config.enable_feishu else '✗'}  "
          f"NURO={'✓' if orch.config.enable_nuro else '✗'}  "
          f"Evolution={'✓' if orch.config.enable_self_evolution else '✗'}")
    print()
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    print()

    orch.start()

    # 主循环：定期打印状态
    try:
        while True:
            time.sleep(60)
            status = orch.get_status()
            running_threads = sum(1 for v in status.get("threads", {}).values() if v)
            print(f"[{time.strftime('%H:%M:%S')}] "
                  f"运行中线程: {running_threads} | "
                  f"Feed循环: {status['stats']['feed_cycles']} | "
                  f"Capture循环: {status['stats']['capture_cycles']} | "
                  f"错误: {status['stats']['errors']}")
    except KeyboardInterrupt:
        pass
    finally:
        orch.stop()


def cmd_status(args):
    """查看全局状态"""
    orch = get_orchestrator(args)
    status = orch.get_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))


def cmd_feed(args):
    """单次资讯拉取"""
    orch = get_orchestrator(args)
    if not orch.feed:
        print("❌ 资讯模块未启用")
        return

    print("📰 拉取最新资讯...")
    items = orch.feed.fetch_latest()
    print(f"获取 {len(items)} 条资讯：\n")

    ctx = orch._build_user_context()
    for item in items:
        score = orch.feed.evaluate_relevance(item, ctx)
        marker = "✓" if score >= 0.5 else "✗"
        print(f"  {marker} [{item.source}] {item.title[:60]}")
        print(f"     相关性: {score:.2f} | {item.url[:80]}")
        print()


def cmd_scan(args):
    """单次采集扫描"""
    orch = get_orchestrator(args)
    if not orch.capture:
        print("❌ 智能采集模块未启用")
        return

    print("🔍 执行采集扫描...")
    observations = orch.capture.scan()

    if not observations:
        print("没有发现异常。")
        return

    print(f"发现 {len(observations)} 个观察：\n")
    for obs in observations:
        severity_icon = "🔴" if obs.severity >= 0.6 else "🟡" if obs.severity >= 0.3 else "🟢"
        print(f"  {severity_icon} [{obs.type}] {obs.title}")
        print(f"     {obs.detail}")
        print(f"     建议: {obs.action}")
        print()


def cmd_chat(args):
    """NURO 聊天"""
    orch = get_orchestrator(args)
    message = " ".join(args.message) if isinstance(args.message, list) else str(args.message)

    if not message:
        # 交互模式
        print("🐾 NURO 聊天模式（输入 'quit' 退出）")
        print()
        while True:
            try:
                user_input = input("你 > ").strip()
            except EOFError:
                break
            if user_input.lower() in ("quit", "exit", "q"):
                break
            if not user_input:
                continue

            reply = orch.chat(user_input)
            print(f"NURO > {reply}")
            print()
    else:
        reply = orch.chat(message)
        print(reply)


def cmd_note(args):
    """写入 Obsidian 笔记"""
    orch = get_orchestrator(args)
    if not orch.obsidian:
        print("❌ Obsidian 模块未启用")
        return

    title = args.title
    content = args.content
    folder = getattr(args, 'folder', '') or ''
    tags = getattr(args, 'tags', '') or ''

    path = orch.write_note(title, content, folder=folder, tags=tags.split(",") if tags else [])
    if path:
        print(f"✅ 笔记已写入: {path}")
    else:
        print("❌ 写入失败")


def cmd_learn(args):
    """记录教训"""
    orch = get_orchestrator(args)
    if not orch.evolution:
        print("❌ 自进化模块未启用")
        return

    scenario = args.scenario
    mistake = args.mistake
    correction = args.correction
    lesson = args.lesson
    category = getattr(args, 'category', 'general')

    result = orch.learn_lesson(scenario, mistake, correction, lesson, category=category)
    if result:
        print(f"✅ 教训已记录: {result.id}")
    else:
        print("❌ 记录失败")


# ── CLI 入口 ──

def main():
    parser = argparse.ArgumentParser(
        description="Alpha-ID Orchestrator CLI — 总调度器命令行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m alpha_id.orchestrate_cli start
  python -m alpha_id.orchestrate_cli start --obsidian-vault "D:/Vault" --git-repos "D:/MW"
  python -m alpha_id.orchestrate_cli feed
  python -m alpha_id.orchestrate_cli scan
  python -m alpha_id.orchestrate_cli chat "你好"
  python -m alpha_id.orchestrate_cli chat          # 交互模式
        """,
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # start
    start_parser = subparsers.add_parser("start", help="启动总调度器（后台循环）")
    start_parser.add_argument("--obsidian-vault", default="", help="Obsidian 笔记库路径")
    start_parser.add_argument("--git-repos", default="", help="逗号分隔的 Git 仓库路径")
    start_parser.add_argument("--feishu-app-id", default="", help="飞书 App ID")
    start_parser.add_argument("--feishu-app-secret", default="", help="飞书 App Secret")

    # status
    subparsers.add_parser("status", help="查看全局状态")

    # feed
    subparsers.add_parser("feed", help="单次资讯拉取")

    # scan
    subparsers.add_parser("scan", help="单次采集扫描")

    # chat
    chat_parser = subparsers.add_parser("chat", help="NURO 聊天")
    chat_parser.add_argument("message", nargs="*", default="", help="消息内容（不传则进入交互模式）")

    # note
    note_parser = subparsers.add_parser("note", help="写入 Obsidian 笔记")
    note_parser.add_argument("--title", required=True, help="笔记标题")
    note_parser.add_argument("--content", required=True, help="笔记内容")
    note_parser.add_argument("--folder", default="", help="子文件夹")
    note_parser.add_argument("--tags", default="", help="逗号分隔的标签")

    # learn
    learn_parser = subparsers.add_parser("learn", help="记录教训")
    learn_parser.add_argument("--scenario", required=True, help="场景")
    learn_parser.add_argument("--mistake", required=True, help="错误")
    learn_parser.add_argument("--correction", required=True, help="正确做法")
    learn_parser.add_argument("--lesson", required=True, help="教训")
    learn_parser.add_argument("--category", default="general", help="分类")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        return

    command_map = {
        "start": cmd_start,
        "status": cmd_status,
        "feed": cmd_feed,
        "scan": cmd_scan,
        "chat": cmd_chat,
        "note": cmd_note,
        "learn": cmd_learn,
    }

    handler = command_map.get(args.command)
    if handler:
        try:
            handler(args)
        except KeyboardInterrupt:
            print("\n已中断")
        except Exception as e:
            print(f"❌ 错误: {e}")
            if args.verbose:
                raise
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
