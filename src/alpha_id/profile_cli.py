"""
Alpha-ID Profile CLI — aid profile / aid collect / aid init

P0 命令：
    aid init                         初始化 ~/.alpha-id/ 目录
    aid collect chatgpt <zip_path>   从 ChatGPT 导出 ZIP 提取画像
    aid profile show                 展示文本画像
    aid profile show --format=json   输出 JSON（供其他工具使用）
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from alpha_id.collectors.chatgpt import collect
from alpha_id.did import DIDRegistry
from alpha_id.profile_schema import (
    QUALITY_EXPORT,
    QUALITY_LOCAL,
    AlphaIDProfile,
    add_collected_source,
    ensure_profile_dir,
    load_profile,
    merge_profile,
    profile_exists,
    save_profile,
    summary,
)


def completeness(profile: AlphaIDProfile) -> dict:
    """计算画像字段完整度"""
    keys = [
        "persona.communication.tone",
        "persona.communication.sentence_length",
        "persona.communication.active_hours",
        "persona.technical.primary_languages",
        "persona.technical.framework_preferences",
        "persona.technical.coding_style",
        "persona.temporal.work_rhythm",
    ]
    present = 0
    missing = []
    for key in keys:
        obj = profile
        for part in key.split("."):
            obj = getattr(obj, part)
        value = obj
        if isinstance(value, (list, tuple)):
            present += 1
        elif value:
            present += 1
        else:
            missing.append(key)
    return {
        "score": round(present / max(len(keys), 1), 2),
        "present_count": present,
        "field_count": len(keys),
        "missing": missing,
    }


logger = logging.getLogger(__name__)
profile_app = typer.Typer(help="Profile 画像管理")
collect_app = typer.Typer(help="数据采集")


def _quality_for(collector_name: str) -> int:
    """根据采集器名推断数据质量"""
    quality_map = {
        "chatgpt": QUALITY_EXPORT,
        "claude": QUALITY_EXPORT,
        "cursor": QUALITY_LOCAL,
        "trae": QUALITY_LOCAL,
        "browser": QUALITY_LOCAL,
    }
    return quality_map.get(collector_name, QUALITY_LOCAL)


@profile_app.command("init")
def cmd_init(
    founder_code: str = typer.Option(None, "--code", "-c", help="创始人验证码（Alpha-1-zx）"),
):
    """初始化 ~/.alpha-id/ 目录结构并生成 DID 身份"""
    ensure_profile_dir()

    # DID 身份（技术底层）
    reg = DIDRegistry()
    did = reg.generate()
    key_dir = Path.home() / ".alpha-id" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "private_key.bin").write_bytes(reg.export_private_key())

    # Alpha-ID 编号（用户可见的身份）
    alpha_id = ""
    if founder_code:
        # 尝试验证创始人代码
        try:
            import hashlib

            founder_code_hash = "2147f64aa8dddda1aa5e6bd13fdebbca87a56b00f7948c9935d17da926a68a29"
            if hashlib.sha256(founder_code.encode()).hexdigest() == founder_code_hash:
                alpha_id = "Alpha-1"
                typer.echo("  [创始人] 验证通过！")
            else:
                typer.echo("  [警告] 创始人验证码无效")
        except Exception:
            pass

    # 创建并保存初始 profile
    profile = AlphaIDProfile(
        did=did,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    if alpha_id:
        profile.extra["alpha_id"] = alpha_id
    save_profile(profile)

    typer.echo("[OK] 已创建目录结构和数字身份")
    typer.echo("   DID: %s" % did)
    if alpha_id:
        typer.echo("   Alpha-ID: %s" % alpha_id)
    typer.echo("")
    typer.echo("  下一步:")
    typer.echo("     aid collect chatgpt <file>   从 ChatGPT 导入")
    typer.echo("     aid wizard start             3 个问题生成画像")
    typer.echo("     aid profile daemon start     后台常驻服务")


@collect_app.command("chatgpt")
def cmd_collect_chatgpt(
    zip_path: str = typer.Argument(..., help="ChatGPT 导出 ZIP 文件路径"),
):
    """从 ChatGPT 导出 ZIP 提取用户画像"""
    p = Path(zip_path)
    if not p.exists():
        typer.echo("[错误] 文件不存在: %s" % p, err=True)
        raise typer.Exit(1)

    profile = collect(p)
    if profile is None:
        typer.echo("[错误] 解析失败，请确认文件是有效的 ChatGPT 导出 ZIP", err=True)
        raise typer.Exit(1)

    profile = merge_profile(profile, source="chatgpt", quality=QUALITY_EXPORT)
    if not profile.did:
        reg = DIDRegistry()
        profile.did = reg.generate()
        key_dir = Path.home() / ".alpha-id" / "keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        (key_dir / "private_key.bin").write_bytes(reg.export_private_key())

    save_profile(profile)
    add_collected_source("chatgpt")
    typer.echo("[OK] 画像已保存")
    typer.echo(summary(profile))
    typer.echo("")
    typer.echo("  下一步:")
    typer.echo("     aid profile web              浏览器查看画像")
    typer.echo("     aid profile daemon start     后台常驻服务")


@collect_app.command("claude")
def cmd_collect_claude(
    zip_path: str = typer.Argument(..., help="Claude 导出 ZIP 文件路径"),
):
    """从 Claude.ai 导出 ZIP 提取用户画像"""
    p = Path(zip_path)
    if not p.exists():
        typer.echo("[错误] 文件不存在: %s" % p, err=True)
        raise typer.Exit(1)

    from alpha_id.collectors.claude import collect as claude_collect

    profile = claude_collect(p)
    if profile is None:
        typer.echo("[错误] 解析失败，请确认文件是有效的 Claude 导出 ZIP", err=True)
        raise typer.Exit(1)

    # 读取已有 DID
    old = load_profile()
    if old and old.did:
        profile.did = old.did
    else:
        reg = DIDRegistry()
        profile.did = reg.generate()
        key_dir = Path.home() / ".alpha-id" / "keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        (key_dir / "private_key.bin").write_bytes(reg.export_private_key())

    save_profile(profile)
    add_collected_source("claude")
    typer.echo("[OK] 画像已保存")
    typer.echo(summary(profile))
    typer.echo("")
    typer.echo("  下一步:")
    typer.echo("     aid profile web              浏览器查看画像")
    typer.echo("     aid profile daemon start     后台常驻服务")


@collect_app.command("cursor")
def cmd_collect_cursor(
    path: str = typer.Argument(..., help="Cursor 导出 ZIP 或 SQLite 数据库文件路径"),
):
    """从 Cursor IDE 提取用户画像"""
    p = Path(path)
    if not p.exists():
        typer.echo("[错误] 文件不存在: %s" % p, err=True)
        raise typer.Exit(1)

    from alpha_id.collectors.cursor import collect as cursor_collect

    profile = cursor_collect(p)
    if profile is None:
        typer.echo("[错误] 解析失败，请确认文件是有效的 Cursor 数据文件", err=True)
        raise typer.Exit(1)

    old = load_profile()
    if old and old.did:
        profile.did = old.did
    else:
        reg = DIDRegistry()
        profile.did = reg.generate()
        key_dir = Path.home() / ".alpha-id" / "keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        (key_dir / "private_key.bin").write_bytes(reg.export_private_key())

    save_profile(profile)
    add_collected_source("cursor")
    typer.echo("[OK] 画像已保存")
    typer.echo(summary(profile))
    typer.echo("")
    typer.echo("  下一步:")
    typer.echo("     aid profile web              浏览器查看画像")
    typer.echo("     aid profile daemon start     后台常驻服务")


@collect_app.command("trae")
def cmd_collect_trae():
    """从 Trae CN 取回代码痕迹"""
    from alpha_id.collectors.trae import collect as trae_collect

    profile = trae_collect()
    if profile is None:
        typer.echo("[错误] 未找到 Trae 数据目录", err=True)
        typer.echo("  预期位置: %%APPDATA%%\\Trae CN\\User", err=True)
        raise typer.Exit(1)

    profile = merge_profile(profile, source="trae", quality=QUALITY_LOCAL)
    if not profile.did:
        from core.did import DIDRegistry

        reg = DIDRegistry()
        profile.did = reg.generate()
        key_dir = Path.home() / ".alpha-id" / "keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        (key_dir / "private_key.bin").write_bytes(reg.export_private_key())

    save_profile(profile)
    add_collected_source("trae")
    from alpha_id.collectors.trae import summary as trae_summary

    typer.echo("[OK] Trae 代码痕迹已采集")
    typer.echo(trae_summary(profile))
    typer.echo("")


@collect_app.command("browser")
def cmd_collect_browser():
    """从浏览器取回书签与历史记录"""
    from alpha_id.collectors.browser import collect as browser_collect

    profile = browser_collect()
    if profile is None:
        typer.echo("[错误] 未找到浏览器数据目录", err=True)
        raise typer.Exit(1)

    profile = merge_profile(profile, source="browser", quality=QUALITY_LOCAL)
    if not profile.did:
        from core.did import DIDRegistry

        reg = DIDRegistry()
        profile.did = reg.generate()
        key_dir = Path.home() / ".alpha-id" / "keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        (key_dir / "private_key.bin").write_bytes(reg.export_private_key())

    save_profile(profile)
    add_collected_source("browser")
    from alpha_id.collectors.browser import summary as browser_summary

    typer.echo("[OK] 浏览器痕迹已采集")
    typer.echo(browser_summary(profile))
    typer.echo("")
    typer.echo("  下一步:")
    typer.echo("     aid profile show              查看完整画像")


@collect_app.command("scan")
def cmd_collect_scan(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="显示详细日志"),
):
    """一键扫描所有可用数据源，自动采集并合并画像"""
    from alpha_id.collectors import discover_instances

    collectors = discover_instances()
    if not collectors:
        typer.echo("  没有发现任何采集器")
        return

    results = []
    for collector in collectors:
        name = collector.info.name
        try:
            detected = collector.detect()
        except Exception:
            detected = False

        if not detected:
            if verbose:
                typer.echo(f"  [跳过] {name}: 未检测到数据")
            continue

        typer.echo(f"  [采集] {name} ...")
        try:
            # 需要路径的采集器（如 chatgpt/claude）尝试自动查找
            if collector.info.requires_input:
                search_dirs = [Path.home() / "Downloads", Path.home() / "Desktop", Path.home() / ".alpha-id"]
                pattern = f"*{name}*"
                found = []
                for d in search_dirs:
                    found.extend(list(d.glob(f"{pattern}.zip")) + list(d.glob(f"{pattern}.json")))
                if not found:
                    typer.echo(f"    [警告] 未找到 {name} 数据文件，请手动指定路径")
                    continue
                profile = collector.collect(found[0])
            else:
                profile = collector.collect()

            if profile is None:
                typer.echo(f"    [警告] {name} 采集返回空结果")
                continue

            profile = merge_profile(profile, source=name, quality=_quality_for(name))
            if not profile.did:
                from alpha_id.did import DIDRegistry

                reg = DIDRegistry()
                profile.did = reg.generate()
                key_dir = Path.home() / ".alpha-id" / "keys"
                key_dir.mkdir(parents=True, exist_ok=True)
                (key_dir / "private_key.bin").write_bytes(reg.export_private_key())

            save_profile(profile)
            add_collected_source(name)
            results.append(name)

            typer.echo(collector.summary(profile))
            typer.echo("")
        except Exception as e:
            typer.echo(f"    [错误] {name}: {e}")
            if verbose:
                import traceback

                traceback.print_exc()

    if results:
        typer.echo(f"[OK] 已从 {len(results)} 个数据源采集: {', '.join(results)}")
    else:
        typer.echo("[提示] 未发现可自动采集的数据源")
        typer.echo("  手动采集: aid collect chatgpt <文件路径>")

    typer.echo("")
    typer.echo("  下一步:")
    typer.echo("     aid profile show              查看画像")


@collect_app.command("list")
def cmd_collect_list():
    """列出所有已注册采集器及其状态"""
    from alpha_id.collectors import discover_instances

    collectors = discover_instances()
    if not collectors:
        typer.echo("  没有发现任何采集器")
        return

    typer.echo("")
    for c in collectors:
        name = c.info.name
        display = c.info.display_name
        try:
            available = c.detect()
        except Exception:
            available = False
        status = "[可用]" if available else "[未检测到]"
        typer.echo(f"  {status} {name:12s} — {display}")
    typer.echo("")


@collect_app.command("scene")
def cmd_collect_scene(
    window_title: Optional[str] = typer.Option(None, "--title", "-t", help="窗口标题"),
    file_path: Optional[str] = typer.Option(None, "--file", "-f", help="文件路径"),
):
    """检测当前工作场景"""
    from alpha_id.scene_detection import detect_scene, format_scene_report

    scene, info = detect_scene(window_title, file_path)
    typer.echo(format_scene_report(scene, info))


@profile_app.command("show")
def cmd_show(
    format: str = typer.Option("text", "--format", "-f", help="输出格式: text | json"),
):
    """展示 profile 画像"""
    if not profile_exists():
        typer.echo("[错误] 尚未生成 profile，请先运行 aid profile mine --path .", err=True)
        raise typer.Exit(1)

    profile = load_profile()
    if profile is None:
        typer.echo("[错误] Profile 解析失败", err=True)
        raise typer.Exit(1)

    if format == "json":
        payload = profile.to_dict()
        payload["x_completeness"] = completeness(profile)
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo("")
    typer.echo("[Alpha-ID] 你的数字身份画像")
    aid = profile.extra.get("alpha_id")
    if aid:
        typer.echo("  身份: %s" % aid)
    typer.echo("  DID: %s" % (profile.did or "未初始化"))
    completeness_info = completeness(profile)
    typer.echo(
        "  完整度: %s%% (%s/%s)"
        % (int(completeness_info["score"] * 100), completeness_info["present_count"], completeness_info["field_count"])
    )
    if completeness_info["missing"]:
        typer.echo("  待补: %s" % ", ".join(completeness_info["missing"]))

    typer.echo("")
    typer.echo("[画像摘要]")
    c = profile.persona.communication
    if c.tone or c.sentence_length or c.active_hours:
        typer.echo("- 沟通: 语气=%s，句长=%s" % (c.tone or "未知", c.sentence_length or "未知"))
        if c.active_hours:
            typer.echo("- 活跃: %s" % ", ".join("%02d:00" % h for h in c.active_hours[:5]))

    t = profile.persona.technical
    if t.primary_languages or t.framework_preferences or t.coding_style:
        typer.echo(
            "- 技术: %s"
            % ", ".join(
                [x for x in [", ".join(t.primary_languages), ", ".join(t.framework_preferences), t.coding_style] if x]
            )
        )
    w = profile.persona.temporal
    if w.work_rhythm:
        typer.echo("- 节奏: %s" % w.work_rhythm)

    provenance = profile.extra.get("x_provenance") or {}
    if provenance:
        typer.echo("")
        typer.echo("[来源追溯]")
        for key, info in provenance.items():
            confidence = info.get("confidence")
            method = info.get("method")
            source = info.get("source")
            typer.echo("- %s: %s%% (%s / %s)" % (key, int((confidence or 0) * 100), method, source))

    typer.echo("")
    typer.echo("_由 Alpha-ID 生成_")


@profile_app.command("web")
@profile_app.command("mine")
def cmd_mine(
    path: str = typer.Option(".", "--path", "-p", help="要扫描的数字痕迹根目录"),
):
    """从本机目录扫描并推断画像，用于快速生成 Ghost Layer 画像"""
    from alpha_id.detect import format_report
    from alpha_id.detect import scan as detect_scan
    from alpha_id.mining.extractor import extract_from_path
    from alpha_id.mining.scanner import scan_path

    scan_root = Path(path)
    if not scan_root.exists():
        typer.echo(f"[错误] 路径不存在: {scan_root}", err=True)
        raise typer.Exit(1)

    typer.echo("[扫描] 先看这个电脑里实际有什么数字痕迹...")
    detected = detect_scan()
    typer.echo(format_report(detected))

    report = scan_path(str(scan_root))
    if not report.sources:
        typer.echo("[提示] 未检测到明显数字痕迹，可尝试更大范围路径")
        raise typer.Exit(0)

    typer.echo(f"[扫描] 目标路径: {scan_root}")
    for source in report.top_sources():
        typer.echo(f"  - {source.kind}: {source.label} ({source.confidence})")

    typer.echo("[推断] 按本机实际痕迹推断画像，不再假设一定有 ChatGPT / Claude ...")
    signals = []
    for item in extract_from_path(str(scan_root)):
        signals.append(
            {
                "source_kind": item.source_kind,
                "source_path": item.source_path,
                "messages": item.messages,
                "timestamps": item.timestamps,
                "code_extensions": item.code_extensions,
                "bookmarks": item.bookmarks,
            }
        )

    if not signals:
        typer.echo("[提示] 扫描到痕迹，但未抽取到可推断信号")
        raise typer.Exit(0)

    profile = infer_profile(signals, seed_did=load_profile().did if load_profile() else "")
    if not profile.did:
        from alpha_id.did import DIDRegistry

        reg = DIDRegistry()
        profile.did = reg.generate()
        key_dir = Path.home() / ".alpha-id" / "keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        (key_dir / "private_key.bin").write_bytes(reg.export_private_key())

    save_profile(profile)
    typer.echo("[OK] 画像已生成/更新")
    typer.echo(summary(profile))


def infer_profile(signals, seed_did: str = "") -> AlphaIDProfile:
    """从抽取信号推断画像，供 CLI 和后续链路复用"""
    from alpha_id.mining.inferrer import infer_profile as _infer_profile

    return _infer_profile(signals, seed_did=seed_did)


def cmd_web(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int = typer.Option(8080, "--port", "-p", help="端口"),
):
    """启动 Ghost Layer 可视化页面 — 你的数字灵魂全景"""
    if not profile_exists():
        typer.echo("[错误] 尚未生成 profile，请先运行 aid profile init", err=True)
        raise typer.Exit(1)

    import json as _json
    import webbrowser

    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="Alpha-ID Ghost Layer")

    # 读取 Ghost Layer HTML 模板
    _template_path = Path(__file__).parent / "templates" / "ghost.html"
    _ghost_html = _template_path.read_text(encoding="utf-8") if _template_path.exists() else ""

    def _inject_profile_data(html: str, profile: AlphaIDProfile) -> str:
        """在 HTML 中注入 profile 数据作为 JS 变量"""
        profile_json = _json.dumps(profile.to_dict(), ensure_ascii=False)
        inject_script = f"<script>\nwindow.__ALPHA_ID_PROFILE__ = {profile_json};\n</script>\n"
        if "</body>" in html:
            return html.replace("</body>", inject_script + "</body>")
        return html + inject_script

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """Ghost Layer 主页面"""
        p = load_profile()
        if p is None:
            return HTMLResponse("<h1>Profile not found</h1>")
        if _ghost_html:
            return HTMLResponse(_inject_profile_data(_ghost_html, p))
        return HTMLResponse(_render_card(p))

    @app.get("/api/profile")
    async def api_profile():
        """Profile JSON API"""
        p = load_profile()
        if p is None:
            return JSONResponse({"error": "Profile not found"}, status_code=404)
        return JSONResponse(p.to_dict())

    @app.get("/card.html", response_class=HTMLResponse)
    async def card():
        """简洁卡片（向后兼容）"""
        p = load_profile()
        if p is None:
            return HTMLResponse("<h1>Profile not found</h1>")
        return HTMLResponse(_render_card(p))

    typer.echo(f"  Ghost Layer → http://{host}:{port}")
    typer.echo(f"  API        → http://{host}:{port}/api/profile")
    webbrowser.open(f"http://{host}:{port}")

    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)


def _render_card(p: AlphaIDProfile) -> str:
    """渲染简洁身份卡片 HTML"""
    aid = p.extra.get("alpha_id", "")

    def _tag(v):
        return f'<span class="tag">{v}</span>' if v else ""

    def _tags(*vals):
        return "".join(_tag(v) for v in vals if v)

    langs = "".join(_tag(lang) for lang in p.persona.technical.primary_languages) or _tag("探索中")
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Alpha-ID 身份卡片</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta property="og:title" content="我的 AI 人格画像">
<meta property="og:description" content="由 Alpha-ID 生成的数字身份">
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:linear-gradient(135deg,#0f172a,#1e293b);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}}
.card{{background:rgba(30,41,59,0.8);backdrop-filter:blur(20px);border:1px solid rgba(148,163,184,0.1);border-radius:24px;padding:40px;max-width:480px;width:100%;box-shadow:0 25px 60px rgba(0,0,0,0.5);}}
.avatar{{width:80px;height:80px;border-radius:50%;background:linear-gradient(135deg,#38bdf8,#818cf8,#c084fc);display:flex;align-items:center;justify-content:center;font-size:32px;color:#fff;margin-bottom:20px;box-shadow:0 8px 24px rgba(56,189,248,0.3);}}
h1{{font-size:24px;color:#f1f5f9;margin-bottom:4px;}}
.did{{font-size:12px;color:#64748b;word-break:break-all;margin-bottom:24px;font-family:monospace;}}
.section{{margin-bottom:20px;}}
.section-title{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;}}
.tag{{display:inline-block;background:rgba(51,65,85,0.6);color:#e2e8f0;padding:6px 14px;border-radius:999px;font-size:13px;margin:3px;border:1px solid rgba(148,163,184,0.08);}}
.footer{{text-align:center;margin-top:32px;font-size:11px;color:#475569;}}
.footer a{{color:#38bdf8;text-decoration:none;}}
</style></head><body>
<div class="card"><div class="avatar">{aid[-1:] if aid else "A"}</div>
<h1>{aid or "Alpha-ID"}</h1>
<div class="did">{p.did}</div>
<div class="section"><div class="section-title">沟通风格</div>{_tags(p.persona.communication.tone, p.persona.communication.sentence_length)}</div>
<div class="section"><div class="section-title">技术偏好</div>{langs}</div>
<div class="section"><div class="section-title">编码风格</div>{_tags(p.persona.technical.coding_style)}</div>
<div class="section"><div class="section-title">工作节奏</div>{_tags(p.persona.temporal.work_rhythm)}</div>
</div>
<div class="footer">由 <a href="https://pypi.org/project/alpha-id-zix/">Alpha-ID</a> 生成</div>
</body></html>"""


@profile_app.command("serve")
def cmd_serve(
    install: bool = typer.Option(False, "--install", help="写入 Claude Desktop 配置"),
):
    """启动 Alpha-ID Profile MCP Server"""
    from alpha_id.profile_mcp_server import main as mcp_main

    mcp_main(install=install)


@profile_app.command("daemon")
def cmd_daemon(
    action: str = typer.Argument("start", help="start | stop | status"),
    port: int = typer.Option(8100, "--port", "-p", help="MCP SSE 端口"),
):
    """后台常驻服务：持续在线，暴露 MCP 身份注入"""
    import subprocess

    pid_file = Path.home() / ".alpha-id" / "daemon.pid"

    if action == "install-startup":
        """注册桌面精灵开机自启（悬浮球）"""
        startup = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup.mkdir(parents=True, exist_ok=True)
        startup_script = startup / "aid_desktop_fairy.bat"
        # aid-daemon 是 pyproject.toml 注册的 entry point
        startup_script.write_text(
            f'@echo off\ncd /d "{Path(__file__).parent.parent}"\nstart /b "" "{sys.executable}" -m aid_daemon\n',
            encoding="utf-8",
        )
        typer.echo("[OK] 桌面精灵已添加到开机启动")
        typer.echo(f"  路径: {startup_script}")
        typer.echo("  下次开机后悬浮球自动出现")
        typer.echo("  取消: 删除该文件即可")
        return

    if action == "stop":
        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            try:
                import subprocess as _sp

                _sp.run(["taskkill", "/f", "/pid", str(pid)], capture_output=True)
                pid_file.unlink()
                typer.echo("[OK] 后台服务已停止")
            except ProcessLookupError:
                typer.echo("[警告] 进程不存在，清理 PID 文件")
                pid_file.unlink()
        else:
            typer.echo("[错误] 后台服务未在运行")
        return

    if action == "status":
        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            try:
                import subprocess as _sp

                _sp.run(["tasklist", "/fi", f"PID eq {pid}"], capture_output=True, text=True)
                typer.echo(f"[OK] 后台服务运行中 (PID: {pid})")
                # 读状态 JSON
                sf = pid_file.with_suffix(".json")
                if sf.exists():
                    import json as _json

                    data = _json.loads(sf.read_text())
                    typer.echo(f"  端口: {data.get('port', '?')}")
                    typer.echo(f"  启动: {data.get('started', '?')}")
            except (ProcessLookupError, PermissionError):
                typer.echo("[警告] PID 文件存在但进程已死，请运行 daemon stop")
        else:
            typer.echo("[状态] 后台服务未运行")
        return

    # start
    if pid_file.exists():
        typer.echo("[错误] 已有后台服务在运行，先运行 daemon stop")
        raise typer.Exit(1)

    script = str(Path(__file__).parent.parent / "aid_mcp_server.py")
    daemon_py = "import subprocess,sys,time,os,json\n"
    daemon_py += f"script={repr(script)}\n"
    daemon_py += f"port={port}\n"
    daemon_py += f"sf={repr(str(pid_file))}\n"
    daemon_py += "os.makedirs(os.path.dirname(sf),exist_ok=True)\n"
    daemon_py += "while True:\n try:\n  p=subprocess.Popen([sys.executable,script,'--transport','sse','--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
    daemon_py += (
        "  open(sf.replace('.pid','.json'),'w').write(json.dumps({'pid':p.pid,'port':port,'status':'running'}))\n"
    )
    daemon_py += "  p.wait()\n except Exception:\n  pass\n time.sleep(2)\n"

    proc = subprocess.Popen(
        [sys.executable, "-c", daemon_py],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    pid_file.write_text(str(proc.pid))
    typer.echo(f"[OK] 后台服务已启动 (PID: {proc.pid})")
    typer.echo(f"  MCP SSE: http://127.0.0.1:{port}")
    typer.echo("  aid profile daemon stop")
