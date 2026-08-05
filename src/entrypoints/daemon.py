"""
NURO Desktop Pet v3 — 纯本地 AI 贾维斯

v2 → v3 重构：
  - 角色：药丸 Dynamic Island → 2D 卡通角色（fairy_character）
  - 大脑：假 FairyBrain 类（不存在）→ MiniCPM-o-4.5 + Ollama（fairy_brain）
  - 语音：Google STT + SAPI TTS → Whisper + Coqui TTS（fairy_voice）
  - 观察：无 → 主动观察循环（fairy_observer）
  - 记忆：独立 fairy_memory.db → 双链记忆（fairy_memory）
  - 身份：无 → FOUNDER → NURO DID 派生（fairy_identity）
  - 通知：无 → 气泡/弹幕/Toast（fairy_popup）
  - 总结：无 → 每日总结 + 锐评（fairy_daily）
  - OCR：内部使用 pytesseract → 仅保留给外部 MCP 客户端
  - Computer Use：复用现有 MCP tools（不新建模块）

v4 重构（当前）：
  - 拆分为子模块：feature_flags, palette, acrylic, daily_summary, cli, app
  - 本文件保留为向后兼容的 re-export shim
  - 新代码请直接从 entrypoints.app / entrypoints.cli 导入

依赖模块（nuro/）:
  fairy_brain, fairy_voice, fairy_character, fairy_observer,
  fairy_popup, fairy_identity, fairy_memory, fairy_daily

VRAM 预算（RTX 5070 Ti 16GB）：
  MiniCPM-o Q4_K_M  ~5.5GB
  Whisper tiny       ~0.5GB（CPU 模式）
  Coqui TTS          ~1.5GB
  CUDA + 系统        ~2.5GB
  Tkinter + 角色     ~0.3GB
  总计               ~10.3GB（剩余 5.7GB）
"""

# ── 向后兼容 re-export ──
# 保持旧导入路径有效：
#   from entrypoints.daemon import AidNuro, main, Palette, apply_acrylic, ...
from entrypoints.acrylic import HAS_DWM_ACRYLIC, apply_acrylic
from entrypoints.app import AidNuro
from entrypoints.cli import _check_ollama, _env_check, _safe_print, main
from entrypoints.daily_summary import (
    compute_next_summary_delay_ms,
    schedule_daily_summary,
    show_daily_summary,
)
from entrypoints.feature_flags import (  # noqa: F401
    _HAS_BRAIN,
    _HAS_CHARACTER,
    _HAS_DAILY,
    _HAS_IDENTITY,
    _HAS_LIST_WINDOWS,
    _HAS_MEMORY,
    _HAS_OBSERVER,
    _HAS_POPUP,
    _HAS_SCREEN,
    _HAS_VOICE,
    _HAS_WINDOW,
    AID_VERSION,
    NURO_VERSION,
    FairyBrain,
    FairyCharacter,
    FairyDaily,
    FairyIdentity,
    FairyMemory,
    FairyObserver,
    FairyPopup,
    FairyState,
    FairyVoice,
    WakeupListener,
    capability_report,
    capture_application_window,
    capture_full_screen,
    capture_region,
    click_on_screen,
    focus_application_window,
    get_mouse_position,
    list_application_windows,
    press_key,
    scroll_mouse,
    type_text,
)
from entrypoints.palette import Palette

__all__ = [
    # 主类
    "AidNuro",
    # CLI
    "main",
    "_safe_print",
    "_check_ollama",
    "_env_check",
    # 子组件
    "Palette",
    "apply_acrylic",
    "HAS_DWM_ACRYLIC",
    "compute_next_summary_delay_ms",
    "schedule_daily_summary",
    "show_daily_summary",
    # 版本
    "NURO_VERSION",
    "AID_VERSION",
    # 能力标志
    "_HAS_BRAIN",
    "_HAS_VOICE",
    "_HAS_CHARACTER",
    "_HAS_OBSERVER",
    "_HAS_POPUP",
    "_HAS_IDENTITY",
    "_HAS_MEMORY",
    "_HAS_DAILY",
    "_HAS_SCREEN",
    "_HAS_WINDOW",
    "_HAS_LIST_WINDOWS",
    "capability_report",
    # 可选模块类（可能为 None）
    "FairyBrain",
    "FairyVoice",
    "WakeupListener",
    "FairyCharacter",
    "FairyState",
    "FairyObserver",
    "FairyPopup",
    "FairyIdentity",
    "FairyMemory",
    "FairyDaily",
    # 工具函数（可能为 None）
    "capture_full_screen",
    "capture_application_window",
    "capture_region",
    "list_application_windows",
    "get_mouse_position",
    "focus_application_window",
    "click_on_screen",
    "type_text",
    "press_key",
    "scroll_mouse",
]
