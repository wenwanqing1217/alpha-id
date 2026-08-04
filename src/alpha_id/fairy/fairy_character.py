"""
NURO Ghost — 角色 shim（向后兼容）

实际实现委托给 alpha_id.ghost_character.GhostCharacter
保持 FairyCharacter / FairyState 别名，使旧代码无需修改。
"""

from alpha_id.ghost_character import GhostCharacter as FairyCharacter  # noqa: F401
from alpha_id.ghost_character import GhostState as FairyState  # noqa: F401

__all__ = ["FairyCharacter", "FairyState"]
