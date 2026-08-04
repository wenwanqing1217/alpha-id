"""
NURO Ghost — Ghost Platform 双链记忆模块（shim）

复用 fairy.fairy_memory，保持接口一致。
"""

from fairy.fairy_memory import FairyMemory as GhostMemory  # noqa: F401

__all__ = ["GhostMemory"]
