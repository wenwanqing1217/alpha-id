# TERM: GhostVoice — 语音模块（STT Whisper + TTS Coqui，shim 复用 fairy.fairy_voice）
"""
NURO Ghost — Ghost Platform 语音模块（shim）

复用 fairy.fairy_voice，保持接口一致。
"""

from fairy.fairy_voice import FairyVoice as GhostVoice  # noqa: F401
from fairy.fairy_voice import WakeupListener  # noqa: F401

__all__ = ["GhostVoice", "WakeupListener"]
