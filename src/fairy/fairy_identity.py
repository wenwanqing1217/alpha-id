"""
NURO 身份 — FOUNDER → NURO DID 派生

FOUNDER 是根身份（高权限），NURO 是从属身份（桌面宠物）。
通过 HMAC-SHA512 派生，确保唯一且可验证。
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Optional, Dict, Any

from core.settings import settings

logger = logging.getLogger(__name__)

NURO_DID_PREFIX = "did:fairy"


class FairyIdentity:
    """
    NURO 去中心化身份

    从 FOUNDER 身份派生，使用 HMAC-SHA512：
    - 输入：FOUNDER_DID + "fairy" + salt
    - 输出：NURO_DID（唯一且可重现）
    """

    def __init__(self, founder_did: Optional[str] = None, salt: Optional[str] = None):
        self.founder_did = founder_did or settings.founder_alpha_id
        self.salt = salt or "fairy_desktop_pet_v3"
        self._fairy_did: Optional[str] = None
        self._created_at = time.time()

    @classmethod
    def from_aid_dir(cls) -> "FairyIdentity":
        """
        从 AID 目录加载 FOUNDER 身份并派生 NURO DID

        Raises:
            FileNotFoundError: 未找到 FOUNDER 身份
        """
        # 尝试从常见位置加载 FOUNDER DID
        aid_dirs = [
            os.path.expanduser("~/.aid"),
            os.path.expanduser("~/.alphaid"),
            os.getenv("AID_DIR", ""),
        ]
        for d in aid_dirs:
            if not d or not os.path.isdir(d):
                continue
            # 查找 identity.json 或 did.json
            for fname in ["identity.json", "did.json", "founder.json"]:
                fpath = os.path.join(d, fname)
                if os.path.exists(fpath):
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    founder_did = data.get("did") or data.get("founder_did") or data.get("id")
                    if founder_did:
                        return cls(founder_did=founder_did)

        # 没找到 FOUNDER 身份
        raise FileNotFoundError(
            "未找到 FOUNDER 身份。请运行 'aid init' 初始化。"
        )

    @property
    def did(self) -> str:
        """NURO DID（兼容 daemon 调用）"""
        return self.fairy_did

    @property
    def fairy_did(self) -> str:
        """获取 NURO DID（懒计算）"""
        if not self._fairy_did:
            self._fairy_did = self._derive_did()
        return self._fairy_did

    @property
    def device_id(self) -> str:
        """设备标识（基于 salt 派生）"""
        return f"fairy-{self.salt[:8]}"

    def _derive_did(self) -> str:
        """
        派生 NURO DID

        HMAC-SHA512(FOUNDER_DID, "fairy" + salt) → 取前 16 字节 hex
        """
        if not self.founder_did:
            # 无 FOUNDER 时使用随机 DID
            random_bytes = os.urandom(32)
            return f"{NURO_DID_PREFIX}:anonymous:{random_bytes[:16].hex()}"

        key = self.founder_did.encode("utf-8")
        msg = f"fairy{self.salt}".encode("utf-8")
        digest = hmac.new(key, msg, hashlib.sha512).hexdigest()
        return f"{NURO_DID_PREFIX}:{self.founder_did.split(':')[-1][:8]}:{digest[:16]}"

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "fairy_did": self.fairy_did,
            "founder_did": self.founder_did,
            "created_at": self._created_at,
            "version": "3.0.0",
        }

    def to_json(self) -> str:
        """序列化为 JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def verify(self, other_did: str) -> bool:
        """验证另一个 DID 是否由此 FOUNDER 派生"""
        if not self.founder_did:
            return False
        key = self.founder_did.encode("utf-8")
        msg = f"fairy{self.salt}".encode("utf-8")
        digest = hmac.new(key, msg, hashlib.sha512).hexdigest()
        expected = f"{NURO_DID_PREFIX}:{self.founder_did.split(':')[-1][:8]}:{digest[:16]}"
        return hmac.compare_digest(expected, other_did)

    def __repr__(self):
        return f"<FairyIdentity did={self.fairy_did[:30]}...>"
