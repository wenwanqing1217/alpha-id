"""
NURO 桌面精灵 — CLI 入口

负责：
  - 命令行参数解析
  - 环境检测模式（--check）
  - 正常启动流程（创建 AidNuro 实例并运行）
  - 安全的跨平台打印（处理 Windows 控制台编码问题）
"""

import argparse
import logging
import sys

from core.http_client import request
from entrypoints.feature_flags import (
    _HAS_BRAIN,
    _HAS_CHARACTER,
    _HAS_DAILY,
    _HAS_IDENTITY,
    _HAS_MEMORY,
    _HAS_OBSERVER,
    _HAS_POPUP,
    _HAS_SCREEN,
    _HAS_VOICE,
    _HAS_WINDOW,
    AID_VERSION,
    NURO_VERSION,
)

logger = logging.getLogger(__name__)


def _safe_print(*args, **kwargs):
    """跨平台安全打印（处理 Windows 控制台 UnicodeEncodeError）"""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        try:
            text = " ".join(str(a) for a in args)
            print(text.encode("utf-8", errors="replace").decode("gbk", errors="replace"), **kwargs)
        except Exception:
            pass


def _check_ollama() -> tuple:
    """检测本地 Ollama 是否运行 + 有哪些模型

    Returns:
        (是否运行, 模型名列表)
    """
    try:
        resp = request("GET", "http://localhost:11434/api/tags", timeout=2)
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        if models:
            _safe_print(f"  Ollama:   ✅ 运行中（{', '.join(models[:3])}）")
            return True, models
        else:
            _safe_print("  Ollama:   ⏳ 运行中但无模型")
            return True, []
    except Exception:
        return False, []


def _env_check():
    """环境检测模式：打印所有能力状态和修复指南"""
    _safe_print("=" * 55)
    _safe_print(f"  NURO 桌面精灵 v{NURO_VERSION} — 环境检测")
    _safe_print("=" * 55)
    _safe_print()
    _safe_print(f"  Python:     {sys.version.split()[0]}")
    _safe_print(f"  AID 版本:   {AID_VERSION}")
    _safe_print()
    _safe_print("  ── NURO 核心能力 ──")
    _safe_print(f"  2D 角色:    {'✅' if _HAS_CHARACTER else '❌'}")
    _safe_print(f"  AI 大脑:    {'✅' if _HAS_BRAIN else '❌'}")
    _safe_print(f"  语音输入:   {'✅' if _HAS_VOICE else '❌'}")
    _safe_print(f"  主动观察:   {'✅' if _HAS_OBSERVER else '❌'}")
    _safe_print(f"  通知系统:   {'✅' if _HAS_POPUP else '❌'}")
    _safe_print(f"  身份派生:   {'✅' if _HAS_IDENTITY else '❌'}")
    _safe_print(f"  双链记忆:   {'✅' if _HAS_MEMORY else '❌'}")
    _safe_print(f"  每日总结:   {'✅' if _HAS_DAILY else '❌'}")
    _safe_print()
    _safe_print("  ── 桌面能力（复用 MCP tools） ──")
    _safe_print(f"  截图:       {'✅' if _HAS_SCREEN else '❌'}")
    _safe_print(f"  窗口控制:   {'✅' if _HAS_WINDOW else '❌'}")
    _safe_print()
    _safe_print("  ── 本地 AI 引擎 ──")
    ollama_running, models = _check_ollama()
    if not ollama_running:
        _safe_print("  Ollama:     ❌ 未运行")
        _safe_print("              下载: https://ollama.com/download")
        _safe_print("              推荐: ollama pull minicpm-o:4.5-4bit")
    _safe_print()
    _safe_print("  ── 依赖安装 ──")
    if not _HAS_VOICE:
        _safe_print("  语音: pip install faster-whisper TTS sounddevice soundfile")
    if not _HAS_CHARACTER:
        _safe_print("  角色: pip install Pillow")
    _safe_print()
    _safe_print("=" * 55)


def main():
    """NURO 桌面精灵 CLI 入口"""
    parser = argparse.ArgumentParser(
        description=f"NURO 桌面精灵 v{NURO_VERSION} — 纯本地 AI 贾维斯"
    )
    parser.add_argument(
        "--version", "-V", action="version",
        version=f"NURO Desktop Pet v{NURO_VERSION}",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="检测环境并打印安装指南（不启动 GUI）",
    )
    parser.add_argument(
        "--no-mcp", action="store_true",
        help="不启动 MCP 后台服务器",
    )
    parser.add_argument(
        "--no-brain", action="store_true",
        help="不加载 LLM 大脑",
    )
    parser.add_argument(
        "--blind", action="store_true",
        help="启动时进入眼瞎耳聋模式（隐私保护）",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="输出调试日志",
    )
    args = parser.parse_args()

    # 标准输出 UTF-8 编码（Windows 兼容性）
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # ── 环境检测模式 ──
    if args.check:
        _env_check()
        return

    # ── 正常启动 ──
    _safe_print("=" * 50)
    _safe_print(f"  NURO Desktop Pet v{NURO_VERSION}")
    _safe_print("  纯本地 AI 贾维斯 · MiniCPM-o-4.5 + Ollama")
    _safe_print("=" * 50)
    _safe_print()

    _has_ollama, models = _check_ollama()
    _safe_print()
    _safe_print(f"  Character:{'✅' if _HAS_CHARACTER else '❌'}")
    _safe_print(f"  Brain:    {'✅' if _HAS_BRAIN else '❌'}")
    _safe_print(f"  Voice:    {'✅' if _HAS_VOICE else '❌'}")
    _safe_print(f"  Observer: {'✅' if _HAS_OBSERVER else '❌'}")
    _safe_print(f"  Popup:    {'✅' if _HAS_POPUP else '❌'}")
    _safe_print(f"  Identity: {'✅' if _HAS_IDENTITY else '❌'}")
    _safe_print(f"  Memory:   {'✅' if _HAS_MEMORY else '❌'}")
    _safe_print(f"  Daily:    {'✅' if _HAS_DAILY else '❌'}")
    _safe_print()

    from core.settings import settings as _settings

    if _HAS_LLM := (_settings.deepseek_api_key or _settings.llm_api_key):  # noqa: N806
        _safe_print("  LLM Key:  ✅ 已配置（备用）")
    if not _HAS_BRAIN and not _has_ollama and not _HAS_LLM:
        _safe_print("  TIP: 安装 Ollama + MiniCPM-o → https://ollama.com")
        _safe_print("       或设置 DEEPSEEK_API_KEY=sk-xxx")
    _safe_print()

    _safe_print("  点击角色 → 打开对话面板")
    _safe_print("  右键 → 快捷菜单（含隐私模式）")
    _safe_print("  语音唤醒 → 「你好 NURO」")
    _safe_print("  拖拽 → 移动位置")
    _safe_print()

    from entrypoints.app import AidNuro

    nuro = AidNuro(
        no_mcp=args.no_mcp,
        no_brain=args.no_brain,
        debug=args.debug,
        blind=args.blind,
    )
    nuro.run()


if __name__ == "__main__":
    main()
