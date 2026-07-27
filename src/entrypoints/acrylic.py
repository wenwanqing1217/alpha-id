"""
NURO 桌面精灵 — DWM 亚克力效果（Win10 1803+ / Win11）

通过 ctypes 调用 SetWindowCompositionAttribute 实现窗口背景模糊。
仅在 Windows 桌面窗口管理器（DWM）可用时生效，其他平台静默跳过。
"""

import ctypes
import sys
from ctypes import wintypes

# ── DWM 可用性 ──
HAS_DWM_ACRYLIC = sys.platform == "win32"


def apply_acrylic(hwnd: int, tint_color: int = 0x1A1A2E, alpha: int = 180) -> bool:
    """为窗口启用 Windows 10/11 亚克力模糊效果

    Args:
        hwnd: 窗口句柄（通过 ctypes.windll.user32.GetParent 获取）
        tint_color: RGB  tint 颜色（默认深紫 #1A1A2E）
        alpha: 透明度 0-255（默认 180，约 70% 不透明）

    Returns:
        是否成功启用
    """
    if not HAS_DWM_ACRYLIC:
        return False

    try:

        class AccentPolicy(ctypes.Structure):
            _fields_ = [
                ("AccentState", wintypes.DWORD),
                ("AccentFlags", wintypes.DWORD),
                ("GradientColor", wintypes.DWORD),
                ("AnimationId", wintypes.DWORD),
            ]

        class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", wintypes.DWORD),
                ("Data", ctypes.POINTER(AccentPolicy)),
                ("SizeOfData", ctypes.c_size_t),
            ]

        # GradientColor 格式：ARGB，alpha 在高 8 位
        gradient = (min(255, alpha) << 24) | (tint_color & 0xFFFFFF)

        accent = AccentPolicy()
        accent.AccentState = 4  # ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.GradientColor = gradient
        accent.AccentFlags = 0
        accent.AnimationId = 0

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.SizeOfData = ctypes.sizeof(accent)
        data.Data = ctypes.pointer(accent)

        ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        return True
    except Exception:
        return False
