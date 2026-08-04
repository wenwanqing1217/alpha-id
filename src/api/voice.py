"""Voice API — GhostVoice (STT/TTS) status endpoint."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/voice", tags=["Voice"])


@router.get("/status")
def voice_status():
    """Check GhostVoice (STT/TTS) availability."""
    try:
        from alpha_id.ghost_voice import GhostVoice

        voice = GhostVoice()
        return {
            "available": voice.is_available(),
            "has_stt": voice.has_stt,
            "has_tts": voice.has_tts,
            "model": {
                "whisper": voice.whisper_model_name,
                "tts": voice.tts_model_name,
            },
        }
    except ImportError:
        return {
            "available": False,
            "has_stt": False,
            "has_tts": False,
            "error": "GhostVoice dependencies not installed",
        }
    except Exception as e:
        return {
            "available": False,
            "has_stt": False,
            "has_tts": False,
            "error": str(e),
        }
