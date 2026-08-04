"""
NURO Ghost — Ghost Platform 观察器模块（shim）

复用 fairy.fairy_observer，保持接口一致。
"""

from fairy.fairy_observer import FairyObserver as GhostObserver  # noqa: F401
from fairy.fairy_observer import SceneType as GhostSceneType  # noqa: F401

__all__ = ["GhostObserver", "GhostSceneType"]
