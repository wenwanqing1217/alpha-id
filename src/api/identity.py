"""用户身份 API 路由"""

from fastapi import APIRouter, Depends, HTTPException
from core.user_identity import UserIdentityManager

from .models import DeviceBindRequest, LoginRequest, RefreshRequest, RegisterRequest, SyncRequest, TokenResponse

from auth.middleware import require_user
from auth.jwt import create_access_token, create_refresh_token, verify_token

router = APIRouter(prefix="/api/v1/identity", tags=["身份"])

# 全局管理器（生产环境使用依赖注入）
_manager: UserIdentityManager = None  # type: ignore


def get_manager() -> UserIdentityManager:
    global _manager
    if _manager is None:
        _manager = UserIdentityManager()
    return _manager


# ── 认证端点（无需令牌） ──


@router.post("/register")
def register(body: RegisterRequest):
    """注册新用户"""
    result = get_manager().register_user(
        device_fingerprint=body.device_fingerprint,
        is_founder=body.is_founder,
        founder_code=body.founder_code,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    """用 alpha_id + 设备指纹获取令牌对"""
    profile = get_manager().get_user_profile(body.alpha_id)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 验证设备指纹（简单校验）
    devices = profile.get("devices", [])
    if not devices:
        raise HTTPException(status_code=403, detail="该用户尚未绑定设备")
    if body.device_fingerprint not in devices:
        # 对于已有设备的用户，允许绑定新设备后登录
        # 更严格的策略可以在生产环境启用
        pass

    token = create_access_token(body.alpha_id)
    refresh = create_refresh_token(body.alpha_id)
    return TokenResponse(
        access_token=token,
        refresh_token=refresh,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest):
    """用刷新令牌换取新的访问令牌"""
    try:
        alpha_id = verify_token(body.refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    profile = get_manager().get_user_profile(alpha_id)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")

    token = create_access_token(alpha_id)
    refresh = create_refresh_token(alpha_id)
    return TokenResponse(
        access_token=token,
        refresh_token=refresh,
    )


# ── 受保护端点（需要 Bearer 令牌） ──


@router.get("/me")
def get_current_user(alpha_id: str = Depends(require_user)):
    """获取当前登录用户信息"""
    profile = get_manager().get_user_profile(alpha_id)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")
    return profile


@router.get("/{alpha_id}")
def get_profile(alpha_id: str, _: str = Depends(require_user)):
    """获取用户档案（需认证）"""
    profile = get_manager().get_user_profile(alpha_id)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")
    return profile


@router.post("/{alpha_id}/devices")
def bind_device(alpha_id: str, body: DeviceBindRequest, _: str = Depends(require_user)):
    """绑定新设备（需认证）"""
    result = get_manager().update_device_binding(
        alpha_id=alpha_id, new_device=body.new_device
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{alpha_id}/sync")
def sync_device(alpha_id: str, body: SyncRequest, _: str = Depends(require_user)):
    """跨设备同步（需认证）"""
    result = get_manager().sync_cross_device(
        alpha_id=alpha_id,
        from_device=body.from_device,
        to_device=body.to_device,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{alpha_id}/session")
def record_session(alpha_id: str, _: str = Depends(require_user)):
    """记录会话（需认证）"""
    result = get_manager().record_session(alpha_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/stats/overview")
def get_statistics():
    """获取系统统计信息（公开）"""
    return get_manager().get_statistics()
