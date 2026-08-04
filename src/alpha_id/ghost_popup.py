"""
NURO Ghost — Ghost Platform 通知模块（shim）

复用 fairy.fairy_popup，保持接口一致。
"""

from fairy.fairy_popup import FairyPopup as GhostPopup  # noqa: F401
from fairy.fairy_popup import PopupType as GhostPopupType  # noqa: F401

__all__ = ["GhostPopup", "GhostPopupType"]
