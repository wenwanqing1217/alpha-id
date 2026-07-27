"""Pydantic 请求/响应模型 — 共享 Schema 模块

所有 API 路由的请求/响应模型统一定义于此，避免重复声明。
web.py（演示应用）保留其独立 Schema，因为其字段形状与正式 API 不同。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

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


class VerifyRequest(BaseModel):
    token: str = Field(..., description="JWT 访问令牌")


class VerifyResponse(BaseModel):
    valid: bool
    alpha_id: str = ""
    token_type: str = ""
    exp: int = 0
    iat: int = 0
    message: str = ""


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


# ── 短剧自动化模块 ──


class ShortDramaSubmitRequest(BaseModel):
    title: str = Field(..., description="短剧标题")
    content: str = Field(..., description="剧本内容或描述")
    content_type: str = Field(default="video", description="内容类型")
    user_id: str = Field(default="default", description="用户ID")


class ShortDramaQueryRequest(BaseModel):
    job_id: str = Field(..., description="审核任务ID")
    user_id: str = Field(default="default", description="用户ID")


class ShortDramaJobResponse(BaseModel):
    success: bool
    status: str
    job_id: str
    title: str
    ai_scan_result: Optional[dict] = None
    review_result: Optional[dict] = None
    created_at: str
    updated_at: str
    message: str = ""


class ShortDramaListResponse(BaseModel):
    success: bool
    total: int
    jobs: List[dict]


# ── 双链记忆模块 ──


class DualChainSaveRequest(BaseModel):
    content: str = Field(..., description="记忆内容")
    category: str = Field(default="general", description="分类")
    sensitivity: int = Field(default=0, ge=0, le=100, description="敏感度 0-100")
    source: str = Field(default="self", description="来源")
    tags: List[str] = Field(default_factory=list, description="标签列表")


class DualChainQueryRequest(BaseModel):
    chain: str = Field(default="all", description="链: private/knowledge/all")
    keyword: str = Field(default="", description="关键词")
    category: str = Field(default="", description="分类过滤")
    max_sensitivity: int = Field(default=100, ge=0, le=100)
    limit: int = Field(default=20, ge=1, le=100)


class DualChainMigrateRequest(BaseModel):
    memory_id: str = Field(..., description="记忆 ID")
    target_chain: str = Field(..., description="目标链: private/knowledge")


# ── Agent 模块 ──


class AgentChatRequest(BaseModel):
    """Agent 对话请求"""

    message: str = Field(..., min_length=1, max_length=4096, description="用户消息")
    use_react: bool = Field(default=False, description="是否使用 ReAct 思考引擎")


class AgentChatResponse(BaseModel):
    """Agent 对话响应"""

    alpha_id: str
    reply: str
    brain_state: str = "idle"


class BrainStatusResponse(BaseModel):
    """大脑状态响应"""

    alpha_id: str
    state: str
    settings: dict


# ── GDPR / 数据主权模块 ──


class GdprDeleteRequest(BaseModel):
    """数据删除请求 — 需要确认码防止误操作"""

    confirmation: str = Field(
        ...,
        description="确认码，必须等于 alpha_id 以确认删除",
    )


class GdprExportResponse(BaseModel):
    """数据导出响应元数据"""

    alpha_id: str
    exported_at: str
    data: Dict[str, Any]
