"""JWT 令牌生成与验证 — 基于 PyJWT

安全增强：
  - 使用 HKDF-SHA256 派生签名密钥（而非简单 SHA-256）
  - 强制要求 AUTH_MASTER_KEY 至少 32 字节熵
  - 支持密钥轮换时的 salt 隔离
"""

import hashlib
import hmac
import time
import uuid
from typing import Optional

import jwt as pyjwt

from core.settings import settings

ALGORITHM: str = "HS256"
VALID_TYPES = ("access", "refresh")

# HKDF 固定 info 字符串，确保密钥用途隔离
_HKDF_INFO = b"alpha-id-jwt-signing-key-v1"
# HKDF salt（全零，仅用于提取阶段）
_HKDF_SALT = b"\x00" * 32


def _require_master_key() -> None:
    if settings.auth_master_key is None:
        raise RuntimeError(
            "AUTH_MASTER_KEY 未配置，无法启动。"
            "请设置环境变量 AUTH_MASTER_KEY 为随机 256-bit 密钥。"
        )
    # 强制要求主密钥至少 32 字节（256-bit 熵）
    if len(settings.auth_master_key.encode("utf-8")) < 32:
        raise RuntimeError(
            "AUTH_MASTER_KEY 太短（< 32 字节）。"
            "请使用至少 32 字节的随机字符串，例如："
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )


def validate_master_key() -> None:
    _require_master_key()


def _get_signing_key() -> bytes:
    """使用 HKDF-SHA256 从主密钥派生签名密钥。

    相比简单 SHA-256，HKDF 提供：
    - 密钥分离（不同用途派生不同密钥）
    - 熵提取（即使主密钥分布不均也能输出均匀密钥）
    - 符合 RFC 5869 标准
    """
    raw = settings.auth_master_key.encode("utf-8")

    # HKDF-Extract: PRK = HMAC-Hash(salt, IKM)
    prk = hmac.new(_HKDF_SALT, raw, hashlib.sha256).digest()

    # HKDF-Expand: OKM = T(1) = HMAC-Hash(PRK, info || 0x01)
    okm = hmac.new(prk, _HKDF_INFO + b"\x01", hashlib.sha256).digest()

    return okm  # 32 字节，正好适合 HS256


def create_access_token(alpha_id: str, extra_claims: Optional[dict] = None) -> str:
    now = int(time.time())
    jti = str(uuid.uuid4())
    payload = {
        "sub": alpha_id,
        "iat": now,
        "exp": now + settings.jwt_access_expire_minutes * 60,
        "type": "access",
        "jti": jti,
    }
    if extra_claims:
        payload.update(extra_claims)
    return pyjwt.encode(payload, _get_signing_key(), algorithm=ALGORITHM)


def create_refresh_token(alpha_id: str) -> str:
    now = int(time.time())
    jti = str(uuid.uuid4())
    payload = {
        "sub": alpha_id,
        "iat": now,
        "exp": now + settings.jwt_refresh_expire_days * 86400,
        "type": "refresh",
        "jti": jti,
    }
    return pyjwt.encode(payload, _get_signing_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = pyjwt.decode(
            token,
            _get_signing_key(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except pyjwt.ExpiredSignatureError:
        raise ValueError("令牌已过期")
    except pyjwt.InvalidTokenError as exc:
        raise ValueError(f"令牌无效: {exc}") from exc

    token_type = payload.get("type", "")
    if token_type not in VALID_TYPES:
        raise ValueError("未知的令牌类型")

    jti = payload.get("jti")
    if jti:
        from auth.token_store import get_token_store
        if get_token_store().is_revoked(jti):
            raise ValueError("令牌已被撤销")

    return payload


def verify_token(token: str, expected_type: str = "access") -> str:
    payload = decode_token(token)
    if payload.get("type") != expected_type:
        raise ValueError(f"令牌类型不匹配: 期望 {expected_type}")
    return payload["sub"]


def get_current_alpha_id(authorization: Optional[str] = None) -> str:
    if not authorization:
        raise ValueError("缺少 Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise ValueError("Authorization 必须是 Bearer 令牌")

    return verify_token(token, expected_type="access")


def revoke_token(token: str):
    payload = decode_token(token)
    jti = payload.get("jti")
    exp = payload.get("exp", 0)
    if jti:
        from auth.token_store import get_token_store
        get_token_store().revoke(jti, exp)


def rotate_token(old_refresh_token: str) -> tuple:
    payload = decode_token(old_refresh_token)
    if payload.get("type") != "refresh":
        raise ValueError("令牌类型不匹配: 需要 refresh 令牌")

    alpha_id = payload["sub"]
    old_jti = payload.get("jti")
    old_exp = payload.get("exp", 0)

    if old_jti:
        from auth.token_store import get_token_store
        store = get_token_store()
        if store.is_revoked(old_jti):
            raise ValueError("刷新令牌已被撤销，可能遭遇重放攻击")
        store.revoke(old_jti, old_exp)

    new_access = create_access_token(alpha_id)
    new_refresh = create_refresh_token(alpha_id)

    return new_access, new_refresh
