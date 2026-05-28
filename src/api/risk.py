"""风控引擎 API 路由"""

from fastapi import APIRouter
from core.risk_engine import (
    BehaviorFingerprint,
    DeviceFingerprint,
    RiskAssessmentEngine,
)

from .models import RiskEvaluateRequest, VoiceVerifyRequest, VoiceVerifyResponse


# ── 共享风控引擎实例 ──

router = APIRouter(prefix="/api/v1/risk", tags=["风控"])

_engine: RiskAssessmentEngine = None  # type: ignore


def get_engine() -> RiskAssessmentEngine:
    global _engine
    if _engine is None:
        _engine = RiskAssessmentEngine()
    return _engine


@router.post("/evaluate")
def evaluate(body: RiskEvaluateRequest):
    """全量风控评估"""
    engine = get_engine()

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
def voice_verify(body: VoiceVerifyRequest):
    """声纹验证专用接口 — 根据声音样本返回匹配度和综合风险"""

    # 此接口可以作为独立验证流程调用，不依赖完整的设备/行为上下文。
    # 实际集成声纹识别模型时，替换 voice_match 为模型推理结果即可。

    voice_data = {
        "voice_match": body.voice_match,
        "habit_match": body.habit_match,
        "noise_level": body.noise_level,
        "audio_quality": body.audio_quality,
    }

    engine = get_engine()
    voice_score = engine.calculate_voice_score(voice_data)

    # 仅用声纹一个维度计算简易风险
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
