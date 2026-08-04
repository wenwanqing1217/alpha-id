# TERM: AlphaID — 身份/AI 服务（JWT 认证依赖注入）
"""FastAPI 认证中间件——依赖注入"""

from typing import Optional

from fastapi import Header, HTTPException, status

from .jwt import get_current_alpha_id


async def require_user(authorization: Optional[str] = Header(None)) -> str:
    """需要有效访问令牌——注入当前 alpha_id

    用法:

        @router.get("/me")
        def get_me(alpha_id: str = Depends(require_user)):
            return {"alpha_id": alpha_id}
    """
    try:
        return get_current_alpha_id(authorization)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def optional_user(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """可选认证（未认证时为 None）"""
    if not authorization:
        return None
    try:
        return get_current_alpha_id(authorization)
    except ValueError:
        return None
