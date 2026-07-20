"""JWT 令牌生成与验证"""

import base64
import hashlib
import hmac
import os
import time
from typing import Optional

# ── 配置（生产环境请从环境变量或密钥管理服务读取） ──

# 密钥衍生参数
MASTER_KEY: Optional[str] = os.environ.get("AUTH_MASTER_KEY")

# 令牌有效期
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("JWT_ACCESS_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("JWT_REFRESH_EXPIRE_DAYS", "7"))

ALGORITHM: str = "HS256"


def _require_master_key() -> None:
    if MASTER_KEY is None:
        raise RuntimeError(
            "AUTH_MASTER_KEY 未配置，无法启动。"
            "请设置环境变量 AUTH_MASTER_KEY 为随机 256-bit 密钥。"
        )


def validate_master_key() -> None:
    """验证 AUTH_MASTER_KEY 是否已配置（启动时调用）"""
    _require_master_key()


# ── 密钥工具 ──


class SecretKey:
    """冻结签名密钥（运行时不变，避免每次签名重新推导）"""

    _instance: Optional["SecretKey"] = None
    _key: bytes

    def __new__(cls) -> "SecretKey":
        if cls._instance is None:
            _require_master_key()
            cls._instance = super().__new__(cls)
            raw = MASTER_KEY.encode("utf-8")
            # 用 SHA-256 将任意长度密钥规范化为 32 字节
            cls._instance._key = hashlib.sha256(raw).digest()
        return cls._instance

    @property
    def bytes(self) -> bytes:
        return self._key

    @property
    def hex(self) -> str:
        return self._key.hex()


# ── 核心函数 ──


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padded = s + "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(padded)


def _hmac_sign(payload_b64: str, key: bytes) -> str:
    """计算 HMAC-SHA256 签名（JWT 标准）"""
    sig = hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(sig)


def create_access_token(alpha_id: str, extra_claims: Optional[dict] = None) -> str:
    """创建访问令牌（短有效期）"""
    now = int(time.time())
    payload = {
        "sub": alpha_id,
        "iat": now,
        "exp": now + ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return _encode(payload)


def create_refresh_token(alpha_id: str) -> str:
    """创建刷新令牌（长有效期）"""
    now = int(time.time())
    payload = {
        "sub": alpha_id,
        "iat": now,
        "exp": now + REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        "type": "refresh",
    }
    return _encode(payload)


def decode_token(token: str) -> dict:
    """解码并验证令牌，返回 payload（无效令牌抛 ValueError）"""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("令牌格式无效")

    header_b64, payload_b64, sig = parts
    key = SecretKey().bytes

    # 验证签名
    expected_sig = _hmac_sign(f"{header_b64}.{payload_b64}", key)
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("签名验证失败")

    # 解码 payload
    try:
        payload_bytes = _b64url_decode(payload_b64)
    except Exception as exc:
        raise ValueError(f"Payload 解码失败: {exc}") from exc

    import json

    try:
        payload: dict = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Payload 不是合法 JSON: {exc}") from exc

    # 验证过期
    now = time.time()
    exp = payload.get("exp", 0)
    if now > exp:
        raise ValueError("令牌已过期")

    # 验证类型
    token_type = payload.get("type", "")
    if token_type not in ("access", "refresh"):
        raise ValueError("未知的令牌类型")

    return payload


def verify_token(token: str, expected_type: str = "access") -> str:
    """验证令牌，成功返回 alpha_id，失败抛 ValueError"""
    payload = decode_token(token)
    if payload.get("type") != expected_type:
        raise ValueError(f"令牌类型不匹配: 期望 {expected_type}")
    return payload["sub"]


def get_current_alpha_id(authorization: Optional[str] = None) -> str:
    """从 Authorization header 提取并验证 alpha_id（FastAPI 依赖用）"""
    if not authorization:
        raise ValueError("缺少 Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise ValueError("Authorization 必须是 Bearer 令牌")

    return verify_token(token, expected_type="access")


# ── 内部编码 ──


def _encode(payload: dict) -> str:
    """编码完整的 JWT（header.payload.signature）"""
    import json

    header = {"alg": ALGORITHM, "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _hmac_sign(f"{header_b64}.{payload_b64}", SecretKey().bytes)
    return f"{header_b64}.{payload_b64}.{sig}"
