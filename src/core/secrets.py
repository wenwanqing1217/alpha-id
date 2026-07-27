"""
密钥安全 — 基于 cryptography.fernet 的对称加密

用途：
- 加密 .env 中的敏感字段（API keys、数据库密码）
- 启动时自动解密，业务代码无感知
- 主密钥从机器指纹派生（或环境变量 SECRET_ENCRYPTION_KEY 指定）

使用方式：
    # 加密（CLI）
    python -m core.secrets encrypt "sk-my-api-key"
    → ENC[gAAAAA...]

    # .env 中使用加密值
    LLM_API_KEY=ENC[gAAAAA...]

    # 启动时自动解密
    from core.secrets import decrypt_if_needed
    value = decrypt_if_needed(os.getenv("LLM_API_KEY"))
"""

import hashlib
import logging
import os
import platform
import socket
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

_ENC_PREFIX = "ENC["

try:
    from cryptography.fernet import Fernet
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
    Fernet = None


def _machine_fingerprint() -> str:
    """获取机器指纹（用于派生主密钥）"""
    parts = [
        platform.node(),
        socket.gethostname(),
        str(uuid.getnode()),
        platform.processor(),
        platform.machine(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_master_key() -> bytes:
    """获取主密钥（环境变量优先，否则用机器指纹派生）"""
    env_key = os.environ.get("SECRET_ENCRYPTION_KEY")
    if env_key:
        # 用户提供的密钥，派生为 Fernet 兼容的 32 字节 base64 key
        import base64
        digest = hashlib.sha256(env_key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    # 机器指纹派生（适合单机部署，换机器需重新加密）
    import base64
    digest = hashlib.sha256(_machine_fingerprint().encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(plaintext: str) -> str:
    """加密明文 → 返回 ENC[...] 格式"""
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography 未安装，无法加密")
    key = _get_master_key()
    f = Fernet(key)
    token = f.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_ENC_PREFIX}{token}]"


def decrypt(encrypted: str) -> str:
    """解密 ENC[...] 格式的字符串"""
    if not _CRYPTO_AVAILABLE:
        logger.warning("cryptography 未安装，无法解密，原样返回")
        return encrypted
    if not encrypted.startswith(_ENC_PREFIX) or not encrypted.endswith("]"):
        return encrypted  # 非加密格式，原样返回
    token = encrypted[len(_ENC_PREFIX):-1]
    key = _get_master_key()
    f = Fernet(key)
    return f.decrypt(token.encode("ascii")).decode("utf-8")


def decrypt_if_needed(value: Optional[str]) -> Optional[str]:
    """如果是 ENC[...] 格式则解密，否则原样返回"""
    if value is None:
        return None
    if isinstance(value, str) and value.startswith(_ENC_PREFIX):
        try:
            return decrypt(value)
        except Exception as e:
            logger.error("解密失败: %s", e)
            return ""
    return value


def is_encrypted(value: Optional[str]) -> bool:
    """判断值是否为加密格式"""
    if not value or not isinstance(value, str):
        return False
    return value.startswith(_ENC_PREFIX) and value.endswith("]")


# ── CLI 入口 ──

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m core.secrets encrypt <plaintext>")
        print("  python -m core.secrets decrypt <ENC[...]>")
        sys.exit(1)

    action = sys.argv[1]
    if action == "encrypt" and len(sys.argv) >= 3:
        print(encrypt(sys.argv[2]))
    elif action == "decrypt" and len(sys.argv) >= 3:
        print(decrypt(sys.argv[2]))
    else:
        print(f"未知操作: {action}")
        sys.exit(1)
