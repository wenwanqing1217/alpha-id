"""用户身份 API 路由"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from alpha_id.container import Container, get_container
from auth.jwt import create_access_token, create_refresh_token, decode_token, revoke_token, rotate_token
from auth.middleware import require_user
from core.user_identity import UserIdentityManager

from .models import DeviceBindRequest, LoginRequest, RefreshRequest, RegisterRequest, SyncRequest, TokenResponse, VerifyRequest, VerifyResponse

router = APIRouter(prefix="/api/v1/identity", tags=["身份"])


def get_manager(container: Container = Depends(get_container)) -> UserIdentityManager:
    """依赖注入：从 Container 获取 UserIdentityManager"""
    return container.identity


# ── 认证端点（无需令牌） ──


@router.post("/register")
def register(body: RegisterRequest, manager: UserIdentityManager = Depends(get_manager)):
    """注册新用户"""
    result = manager.register_user(
        device_fingerprint=body.device_fingerprint,
        is_founder=body.is_founder,
        founder_code=body.founder_code,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, manager: UserIdentityManager = Depends(get_manager)):
    """用 alpha_id + 设备指纹获取令牌对"""
    profile = manager.get_user_profile(body.alpha_id)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 验证设备指纹（简单校验）
    devices = profile.get("devices", [])
    if not devices:
        raise HTTPException(status_code=403, detail="该用户尚未绑定设备")
    if body.device_fingerprint not in devices:
        raise HTTPException(status_code=403, detail="设备未绑定，请先绑定设备")

    token = create_access_token(body.alpha_id)
    refresh = create_refresh_token(body.alpha_id)
    return TokenResponse(
        access_token=token,
        refresh_token=refresh,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest):
    """用刷新令牌轮换新的令牌对（旧 refresh token 立即失效）"""
    try:
        new_access, new_refresh = rotate_token(body.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
    )


@router.post("/logout")
def logout(
    authorization: Optional[str] = Header(None),
    _: str = Depends(require_user),
):
    """登出：撤销当前 access token（将 jti 加入黑名单）"""
    # 从 Authorization header 提取原始 token 并撤销
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                revoke_token(token)
            except ValueError:
                # 令牌已过期或无效，无需撤销
                pass
    return {"success": True, "message": "已登出，令牌已撤销"}


# ── 跨服务验证端点（供其他项目验证 AID 签发的 JWT） ──


@router.post("/auth/verify", response_model=VerifyResponse)
def auth_verify(body: VerifyRequest):
    """验证 AID 签发的 JWT 令牌（公开，供跨服务验证）"""
    try:
        payload = decode_token(body.token)
        return VerifyResponse(
            valid=True,
            alpha_id=payload.get("sub", ""),
            token_type=payload.get("type", ""),
            exp=payload.get("exp", 0),
            iat=payload.get("iat", 0),
        )
    except ValueError as exc:
        return VerifyResponse(valid=False, message=str(exc))


# ── 受保护端点（需要 Bearer 令牌） ──


@router.get("/me")
def get_current_user(alpha_id: str = Depends(require_user),
                     manager: UserIdentityManager = Depends(get_manager)):
    """获取当前用户信息（需认证）"""
    profile = manager.get_user_profile(alpha_id)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 脱敏：不暴露 device_fingerprint
    safe = {k: v for k, v in profile.items() if k != "device_fingerprint"}
    return safe


@router.get("/{alpha_id}")
def get_user_profile(alpha_id: str,
                     _: str = Depends(require_user),
                     manager: UserIdentityManager = Depends(get_manager)):
    """获取指定用户档案（需认证）"""
    profile = manager.get_user_profile(alpha_id)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")
    return profile


@router.post("/{alpha_id}/devices")
def bind_device(alpha_id: str,
                body: DeviceBindRequest,
                _: str = Depends(require_user),
                manager: UserIdentityManager = Depends(get_manager)):
    """绑定新设备（需认证）"""
    result = manager.update_device_binding(alpha_id=alpha_id, new_device=body.new_device)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{alpha_id}/sync")
def sync_device(alpha_id: str,
                body: SyncRequest,
                _: str = Depends(require_user),
                manager: UserIdentityManager = Depends(get_manager)):
    """跨设备同步（需认证）"""
    result = manager.sync_cross_device(
        alpha_id=alpha_id,
        from_device=body.from_device,
        to_device=body.to_device,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{alpha_id}/session")
def record_session(alpha_id: str,
                   _: str = Depends(require_user),
                   manager: UserIdentityManager = Depends(get_manager)):
    """记录会话（需认证）"""
    result = manager.record_session(alpha_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/stats/overview")
def get_statistics(manager: UserIdentityManager = Depends(get_manager)):
    """获取系统统计信息（公开）"""
    return manager.get_statistics()
