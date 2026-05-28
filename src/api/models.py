"""Pydantic 请求/响应模型"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional


# ── 认证模块 ──

class LoginRequest(BaseModel):
    alpha_id: str
    device_fingerprint: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_minutes: int = 30


class RefreshRequest(BaseModel):
    refresh_token: str


# ── 身份模块 ──

class RegisterRequest(BaseModel):
    device_fingerprint: str = Field(..., description="设备指纹")
    is_founder: bool = False
    founder_code: Optional[str] = None


class DeviceBindRequest(BaseModel):
    new_device: str = Field(..., description="新设备指纹")


class SyncRequest(BaseModel):
    from_device: str = Field(..., description="源设备")
    to_device: str = Field(..., description="目标设备")


# ── 社交模块 ──

class FriendRequestSend(BaseModel):
    from_alpha_id: str
    to_alpha_id: str
    message: str = ""


class FriendRequestRespond(BaseModel):
    response: str = Field(..., pattern="^(accept|reject)$", description="accept or reject")


class MessageSend(BaseModel):
    from_alpha_id: str
    to_alpha_id: str
    content: str
    message_type: str = "text"


class MessageQuery(BaseModel):
    unread_only: bool = False


# ── 风控模块 ──

class DeviceFingerprintModel(BaseModel):
    hardware_id: str
    ip_address: str
    location: str
    browser_info: str
    screen_resolution: str
    first_access_time: str


class BehaviorFingerprintModel(BaseModel):
    typing_speed: float = 0.0
    session_time: str = "00:00"
    common_words: List[str] = []
    error_rate: float = 0.0
    word_count: int = 0
    emoji_count: int = 0
    mouse_movement: int = 0
    input_pattern: str = ""
    language: str = "zh"


class VoiceDataModel(BaseModel):
    voice_match: float = 0.0
    habit_match: float = 0.0
    noise_level: float = 0.0
    audio_quality: float = 0.0


class VoiceVerifyRequest(BaseModel):
    """声纹验证请求"""
    user_id: str
    voice_sample_id: str = ""
    device_fingerprint: str = ""
    voice_match: float = Field(default=0.0, ge=0.0, le=1.0, description="声纹匹配度")
    habit_match: float = Field(default=0.0, ge=0.0, le=1.0, description="语音习惯匹配度")
    noise_level: float = Field(default=0.0, ge=0.0, le=1.0, description="环境噪声等级")
    audio_quality: float = Field(default=0.0, ge=0.0, le=1.0, description="音频质量")


class VoiceVerifyResponse(BaseModel):
    """声纹验证响应"""
    voice_score: float
    risk_score: float
    risk_level: str
    action_required: str
    recommended_verification: str


class RiskEvaluateRequest(BaseModel):
    device_current: Optional[DeviceFingerprintModel] = None
    behavior_current: Optional[BehaviorFingerprintModel] = None
    voice_data: Optional[VoiceDataModel] = None
