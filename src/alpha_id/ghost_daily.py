"""
NURO Ghost — Ghost Platform 每日总结模块（shim）

复用 fairy.fairy_daily，保持接口一致。
"""

from fairy.fairy_daily import FairyDaily as GhostDaily  # noqa: F401

__all__ = ["GhostDaily"]
