"""风控引擎 API 路由"""

from fastapi import APIRouter, Depends

from alpha_id.container import Container, get_container
from core.risk_engine import (
    BehaviorFingerprint,
    DeviceFingerprint,
    RiskAssessmentEngine,
)

from .models import RiskEvaluateRequest, VoiceVerifyRequest, VoiceVerifyResponse

router = APIRouter(prefix="/api/v1/risk", tags=["风控"])


def get_engine(container: Container = Depends(get_container)) -> RiskAssessmentEngine:
    """依赖注入：从 Container 获取 RiskAssessmentEngine"""
    return container.risk


@router.post("/evaluate")
def evaluate(body: RiskEvaluateRequest,
             engine: RiskAssessmentEngine = Depends(get_engine)):
    """全量风控评估（公开）"""
    device_current = None
    behavior_current = None
    voice_data = None

    if body.device_current:
        device_current = DeviceFingerprint(
            hardware_id=body.device_current.hardware_id,
            ip_address=body.device_current.ip_address,
            location=body.device_current.location,
            browser_info=body.device_current.browser_info,
            first_access_time=body.device_current.first_access_time,
            screen_resolution=body.device_current.screen_resolution,
        )

    if body.behavior_current:
        behavior_current = BehaviorFingerprint(
            typing_speed=body.behavior_current.typing_speed,
            mouse_movement=body.behavior_current.mouse_movement,
            session_time=body.behavior_current.session_time,
            input_pattern=body.behavior_current.input_pattern,
            language=body.behavior_current.language,
        )

    if body.voice_data:
        voice_data = {
            "voice_match": body.voice_data.voice_match,
            "habit_match": body.voice_data.habit_match,
            "noise_level": body.voice_data.noise_level,
            "audio_quality": body.voice_data.audio_quality,
        }

    device_score = engine.calculate_device_score(device_current, None)
    behavior_score = engine.calculate_behavior_score(behavior_current) if behavior_current else 50.0
    voice_score = engine.calculate_voice_score(voice_data)
    risk_score = engine.calculate_total_risk(device_score, behavior_score, voice_score)
    risk_level = engine.determine_risk_level(risk_score)
    action = engine.get_action_required(risk_level, risk_score)
    verification = engine.get_recommended_verification(risk_level)

    return {
        "risk_score": round(risk_score, 2),
        "risk_level": risk_level,
        "device_score": round(device_score, 2),
        "behavior_score": round(behavior_score, 2),
        "voice_score": round(voice_score, 2),
        "action_required": action,
        "recommended_verification": verification,
    }


@router.post("/voice-verify")
def voice_verify(body: VoiceVerifyRequest,
                 engine: RiskAssessmentEngine = Depends(get_engine)):
    """声纹验证专用接口（公开）"""

    voice_data = {
        "voice_match": body.voice_match,
        "habit_match": body.habit_match,
        "noise_level": body.noise_level,
        "audio_quality": body.audio_quality,
    }

    voice_score = engine.calculate_voice_score(voice_data)
    risk_score = 100.0 - voice_score
    risk_level = engine.determine_risk_level(risk_score)
    action = engine.get_action_required(risk_level, risk_score)
    verification = engine.get_recommended_verification(risk_level)

    return VoiceVerifyResponse(
        voice_score=round(voice_score, 2),
        risk_score=round(risk_score, 2),
        risk_level=risk_level,
        action_required=action,
        recommended_verification=verification,
    )
