"""
Alpha-ID 一键运行管道 — 采集 → 理解 → 存储 → 报告
===================================================
把整个流程串起来，一条命令跑完。

用法：
  # 自动检测豆包数据源，分析，存储，出报告
  python -m alpha_id.enrichment.run_pipeline

  # 指定方式
  python -m alpha_id.enrichment.run_pipeline --method leveldb
  python -m alpha_id.enrichment.run_pipeline --method export --path ./exports/
  python -m alpha_id.enrichment.run_pipeline --method directory --path ./texts/

  # 指定模型（不指定则自动选免费额度）
  python -m alpha_id.enrichment.run_pipeline --model deepseek/deepseek-chat

  # 只看报告，不重新采集
  python -m alpha_id.enrichment.run_pipeline --report-only
"""

import argparse
import logging
import sys
from pathlib import Path

# 确保项目根在 path 里
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from alpha_id.enrichment.llm_enricher import LLMEnricher
from alpha_id.enrichment.doubao_collector import DoubaoCollector
from alpha_id.enrichment.profile_store import ProfileStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("alpha-id-pipeline")


def main():
    parser = argparse.ArgumentParser(
        description="Alpha-ID 数据管道 — 采集对话 → LLM 理解 → 本地画像",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m alpha_id.enrichment.run_pipeline
  python -m alpha_id.enrichment.run_pipeline --method leveldb
  python -m alpha_id.enrichment.run_pipeline --method export --path ./my_chats/
  python -m alpha_id.enrichment.run_pipeline --report-only
        """,
    )
    parser.add_argument("--method", default="auto", choices=["auto", "leveldb", "export", "manual", "directory"],
                        help="数据采集方式（默认 auto）")
    parser.add_argument("--path", default="", help="导出文件/目录路径（manual 模式下直接作为文本）")
    parser.add_argument("--model", default="", help="LLM 模型（不指定则自动选免费额度）")
    parser.add_argument("--report-only", action="store_true", help="只生成报告，不采集")
    parser.add_argument("--dry-run", action="store_true", help="只采集不分析（看有多少数据）")
    parser.add_argument("--text", default="", help="直接输入对话文本（manual 模式）")

    args = parser.parse_args()

    print("""
╔══════════════════════════════════════════════════╗
║        Alpha-ID 数据管道 v1.0                    ║
║   采集 → 理解 → 存储 → 报告                       ║
╚══════════════════════════════════════════════════╝
    """)

    # ─── 初始化 ────────────────────────────────────────────
    store = ProfileStore()
    enricher = LLMEnricher(model=args.model) if not args.dry_run else None

    # ─── 报告模式 ─────────────────────────────────────────
    if args.report_only:
        _show_report(store)
        return

    # ─── 采集 ─────────────────────────────────────────────
    collector = DoubaoCollector()
    collect_kwargs = {}
    if args.method == "manual":
        # manual 模式：--text 或 --path 都作为文本输入
        text = args.text or args.path
        collect_kwargs["text"] = text
    elif args.path:
        if args.method == "export":
            collect_kwargs["files"] = [Path(p) for p in args.path.split(",")]
        elif args.method == "directory":
            collect_kwargs["directory"] = args.path

    logger.info("开始采集 — 方式: %s", args.method)
    conversations = collector.collect(method=args.method, **collect_kwargs)

    if not conversations:
        print("\n⚠️  未采集到任何数据。请检查：")
        print("  1. 豆包桌面端是否运行过？")
        print("  2. 是否有导出文件放在 Downloads/Desktop？")
        print("  3. 或手动方式：--method manual --path '你的对话文本'")
        sys.exit(1)

    print(f"\n✅ 采集完成: {len(conversations)} 条对话")

    # 只看数量，不分析
    if args.dry_run:
        print("\n📊 数据预览：")
        for i, conv in enumerate(conversations[:5]):
            text_len = len(conv.get("text", ""))
            source = conv.get("source", "unknown")
            print(f"  [{i+1}] {source} — {text_len} 字符")
        if len(conversations) > 5:
            print(f"  ... 还有 {len(conversations) - 5} 条")
        print(f"\n总计: {len(conversations)} 条对话")
        return

    # ─── 理解（LLM 分析） ──────────────────────────────────
    logger.info("开始 LLM 分析 — 模型: %s", enricher.model)
    print(f"\n🧠 正在分析（模型: {enricher.model}）...")

    for i, conv in enumerate(conversations):
        text = conv.get("text", "")
        source = conv.get("source", "unknown")
        if len(text) < 50:
            continue

        # 保存原始对话
        store.save_conversation(conv)

        # LLM 分析
        result = enricher.analyze(text, source=source)
        store.save_enrichment(result)

        # 进度
        if (i + 1) % 5 == 0 or i == len(conversations) - 1:
            print(f"  进度: {i+1}/{len(conversations)}")

    # ─── 输出结果 ──────────────────────────────────────────
    _show_report(store)
    
    print(f"\n📊 管道统计:")
    print(f"  分析调用: {enricher.stats['call_count']} 次")
    print(f"  数据来源: {len(store.get_data_sources())} 个")
    print(f"  数据库: {store.db}")


def _show_report(store: ProfileStore):
    """显示当前画像报告"""
    profile = store.get_merged_profile()
    sources = store.get_data_sources()

    print("\n" + "=" * 50)
    print("📋 Alpha-ID 画像报告")
    print("=" * 50)

    tech = profile.get("technical", {})
    if tech:
        if tech.get("languages"):
            print(f"\n🔧 技术栈:")
            for lang, level in tech["languages"].items():
                bar = "█" * {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}.get(str(level).lower(), 0)
                print(f"    {lang}: {level} {bar}")

        if tech.get("frameworks"):
            print(f"\n📦 框架: {', '.join(tech['frameworks'])}")
        if tech.get("tools"):
            print(f"🛠️  工具: {', '.join(tech['tools'])}")
        if tech.get("domains"):
            print(f"🎯 领域: {', '.join(tech['domains'])}")
        if tech.get("current_projects"):
            print(f"🚀 当前项目:")
            for p in tech["current_projects"]:
                print(f"    • {p}")
        if tech.get("learning"):
            print(f"📚 正在学习: {', '.join(tech['learning'])}")

    comm = profile.get("communication", {})
    if any(comm.values()):
        print(f"\n💬 沟通风格:")
        if comm.get("tone"):
            print(f"    语气: {comm['tone']}")
        if comm.get("style"):
            print(f"    思维: {comm['style']}")

    work = profile.get("work_pattern", {})
    if any(v for v in work.values() if v):
        print(f"\n⏰ 工作模式:")
        if work.get("rhythm"):
            print(f"    节奏: {'夜猫子' if work['rhythm'] == 'night_owl' else '日间型'}")
        if work.get("peak_hours"):
            print(f"    高峰: {', '.join(f'{h:02d}:00' for h in work['peak_hours'][:5])}")
        if work.get("recent_focus"):
            print(f"    焦点: {work['recent_focus']}")

    if sources:
        print(f"\n📊 数据来源:")
        for s in sources:
            print(f"    {s['name']}: {s['item_count']} 条（最近: {s['last_collected'][:10]}）")

    # 导出 Markdown
    report_path = store.export_markdown()
    print(f"\n📝 完整报告已保存: {report_path}")
    print("=" * 50)


if __name__ == "__main__":
    main()
