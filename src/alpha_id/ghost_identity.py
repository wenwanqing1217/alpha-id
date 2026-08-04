"""
NURO Ghost — Ghost Platform 身份模块（shim）

复用 fairy.fairy_identity，保持接口一致。
"""

from fairy.fairy_identity import FairyIdentity as GhostIdentity  # noqa: F401

__all__ = ["GhostIdentity"]
