"""
NURO Ghost — 大脑 shim（向后兼容）

实际实现委托给 alpha_id.ghost_brain.GhostBrain
保持 FairyBrain 别名，使旧代码无需修改。
"""

from alpha_id.ghost_brain import GhostBrain as FairyBrain  # noqa: F401

__all__ = ["FairyBrain"]
