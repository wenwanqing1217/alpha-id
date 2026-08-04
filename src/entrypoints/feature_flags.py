"""
NURO 桌面精灵 — 功能标志与可选模块导入

所有 `_HAS_*` 标志集中在同一处，便于：
  - 统一查看当前环境能力
  - 单元测试时 monkeypatch
  - 新模块接入时遵循同样的优雅降级模式

每个 try/except 块只负责一个能力域，失败时静默降级。
"""

from tools.screen_capture import (
    capture_full_screen,
    capture_application_window,
    capture_region,
)

# ── 版本 ──
try:
    from fairy import __version__ as NURO_VERSION
except ImportError:
    NURO_VERSION = "3.0.0"

try:
    from alpha_id import __version__ as AID_VERSION
except ImportError:
    AID_VERSION = "0.2.0"

# ── 大脑 ──
_HAS_BRAIN = False
GhostBrain = None
try:
    from alpha_id.ghost_brain import GhostBrain  # noqa: F811

    _HAS_BRAIN = True
except ImportError:
    pass

# ── 语音 ──
_HAS_VOICE = False
GhostVoice = None
WakeupListener = None
try:
    from alpha_id.ghost_voice import GhostVoice, WakeupListener  # noqa: F811

    _HAS_VOICE = True
except ImportError:
    pass

# ── 角色 ──
_HAS_CHARACTER = False
GhostCharacter = None
GhostState = None
try:
    from alpha_id.ghost_character import GhostCharacter, GhostState  # noqa: F811

    _HAS_CHARACTER = True
except ImportError:
    pass

# ── 观察器 ──
_HAS_OBSERVER = False
GhostObserver = None
try:
    from alpha_id.ghost_observer import GhostObserver  # noqa: F811

    _HAS_OBSERVER = True
except ImportError:
    pass

# ── 通知气泡 ──
_HAS_POPUP = False
GhostPopup = None
try:
    from alpha_id.ghost_popup import GhostPopup  # noqa: F811

    _HAS_POPUP = True
except ImportError:
    pass

# ── 身份派生 ──
_HAS_IDENTITY = False
GhostIdentity = None
try:
    from alpha_id.ghost_identity import GhostIdentity  # noqa: F811

    _HAS_IDENTITY = True
except ImportError:
    pass

# ── 双链记忆 ──
_HAS_MEMORY = False
GhostMemory = None
try:
    from alpha_id.ghost_memory import GhostMemory  # noqa: F811

    _HAS_MEMORY = True
except ImportError:
    pass

# ── 每日总结 ──
_HAS_DAILY = False
GhostDaily = None
try:
    from alpha_id.ghost_daily import GhostDaily  # noqa: F811

    _HAS_DAILY = True
except ImportError:
    pass

# ── 截图工具 ──
_HAS_SCREEN = False
capture_full_screen = None  # type: ignore[assignment]
capture_application_window = None  # type: ignore[assignment]
capture_region = None  # type: ignore[assignment]
try:
    from tools.screen_capture import (  # noqa: F811
        capture_full_screen,
        capture_application_window,
        capture_region,
    )

    _HAS_SCREEN = True
except ImportError:
    pass

# ── 窗口枚举 ──
_HAS_LIST_WINDOWS = False
list_application_windows = None  # type: ignore[assignment]
try:
    from tools.screen_capture import list_application_windows as _list_app_windows  # noqa: F811

    list_application_windows = _list_app_windows
    _HAS_LIST_WINDOWS = True
except ImportError:
    pass

# ── 窗口控制工具 ──
_HAS_WINDOW = False
get_mouse_position = None  # type: ignore[assignment]
focus_application_window = None  # type: ignore[assignment]
click_on_screen = None  # type: ignore[assignment]
type_text = None  # type: ignore[assignment]
press_key = None  # type: ignore[assignment]
scroll_mouse = None  # type: ignore[assignment]
try:
    from tools.window_control import (  # noqa: F811
        get_mouse_position,
        focus_application_window,
        click_on_screen,
        type_text,
        press_key,
        scroll_mouse,
    )

    _HAS_WINDOW = True
except ImportError:
    pass


# ── 向后兼容别名（daemon.py re-export shim 使用 Fairy* 命名）──
FairyBrain = GhostBrain
FairyCharacter = GhostCharacter
FairyDaily = GhostDaily
FairyIdentity = GhostIdentity
FairyMemory = GhostMemory
FairyObserver = GhostObserver
FairyPopup = GhostPopup
FairyState = GhostState
FairyVoice = GhostVoice


def capability_report() -> dict:
    """返回所有能力标志的快照，用于环境检测与日志"""
    return {
        "character": _HAS_CHARACTER,
        "brain": _HAS_BRAIN,
        "voice": _HAS_VOICE,
        "observer": _HAS_OBSERVER,
        "popup": _HAS_POPUP,
        "identity": _HAS_IDENTITY,
        "memory": _HAS_MEMORY,
        "daily": _HAS_DAILY,
        "screen": _HAS_SCREEN,
        "window": _HAS_WINDOW,
        "list_windows": _HAS_LIST_WINDOWS,
    }
