"""
AIDSigner — Agent Identity 签名/验签 SDK

为 Python 程序提供 DID 签名、验签接口，封装 DIDRegistry。

用法：
    signer = AIDSigner()
    signer.generate()                 # 新身份
    signer.load("~/.aid/identity.priv")  # 从文件加载

    sig = signer.sign_file("config.yaml")
    ok  = signer.verify_file("config.yaml", sig)
"""

import json
import logging
from pathlib import Path
from typing import Optional, Union

from alpha_id.did import DIDDocument, DIDRegistry

logger = logging.getLogger(__name__)


class AIDSigner:
    """Agent DID 签名/验签 SDK

    核心能力：
    - 生成/加载 DID 身份
    - 对字节数据或文件签名
    - 验证签名（本地公钥或指定 DID）
    - 导出/导入 DID Document
    """

    def __init__(self, registry: Optional[DIDRegistry] = None):
        self._reg = registry or DIDRegistry()

    # ── 身份管理 ──

    def generate(self) -> str:
        """生成新 DID + Ed25519 密钥对，返回 did

        >>> signer = AIDSigner()
        >>> did = signer.generate()
        >>> did.startswith("did:aid:")
        True
        """
        return self._reg.generate()

    def load_private_key(self, path: Union[str, Path]) -> str:
        """从私钥文件加载身份

        Args:
            path: 私钥文件路径（raw bytes 32字节 seed）

        Returns:
            did 字符串
        """
        priv_bytes = Path(path).expanduser().read_bytes()
        return self._reg.from_private_key_bytes(priv_bytes)

    def load_private_key_from_bytes(self, private_bytes: bytes) -> str:
        """从私钥 bytes 加载身份

        Args:
            private_bytes: 32字节 Ed25519 私钥 seed

        Returns:
            did 字符串
        """
        return self._reg.from_private_key_bytes(private_bytes)

    @property
    def did(self) -> Optional[str]:
        """当前 DID"""
        return self._reg.did

    @property
    def public_key(self) -> Optional[bytes]:
        """当前公钥（raw bytes）"""
        return self._reg.public_key

    @property
    def has_identity(self) -> bool:
        """是否已初始化身份"""
        return self._reg.did is not None

    # ── 签名 ──

    def sign(self, payload: bytes) -> bytes:
        """对字节数据签名，返回 64 字节 Ed25519 签名

        Raises:
            ValueError: 未初始化身份
        """
        return self._reg.sign(payload)

    def sign_file(self, file_path: Union[str, Path]) -> bytes:
        """对文件内容签名

        Args:
            file_path: 文件路径

        Returns:
            64 字节签名

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 未初始化身份
        """
        data = Path(file_path).expanduser().read_bytes()
        sig = self._reg.sign(data)
        # 同时写入 .sig 文件
        sig_path = Path(str(file_path) + ".sig")
        sig_path.write_bytes(sig)
        return sig

    def sign_json(self, obj: dict) -> bytes:
        """对 JSON 对象（规范序列化后）签名"""
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        return self._reg.sign(canonical)

    # ── 验签 ──

    def verify(self, payload: bytes, signature: bytes, public_key: Optional[bytes] = None) -> bool:
        """验证字节数据签名

        Args:
            payload: 原始数据
            signature: 64字节签名
            public_key: 公钥（默认用当前身份公钥）

        Returns:
            True 验证通过
        """
        pk = public_key if public_key is not None else self._reg.public_key
        if pk is None:
            raise ValueError("No public key available — load identity or pass public_key")
        return DIDRegistry.verify(pk, payload, signature)

    def verify_file(
        self, file_path: Union[str, Path], signature: Optional[bytes] = None, public_key: Optional[bytes] = None
    ) -> bool:
        """验证文件签名

        Args:
            file_path: 原始文件路径
            signature: 签名 bytes（默认自动读取 .sig 后缀文件）
            public_key: 公钥（默认用当前身份）

        Returns:
            True 验证通过
        """
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 自动查找签名文件
        sig = signature
        if sig is None:
            sig_path = Path(str(path) + ".sig")
            if sig_path.exists():
                sig = sig_path.read_bytes()
        if sig is None:
            raise FileNotFoundError(f"No signature found for {file_path}")

        data = path.read_bytes()
        return self.verify(data, sig, public_key)

    def verify_json(self, obj: dict, signature: bytes, public_key: Optional[bytes] = None) -> bool:
        """验证 JSON 对象签名"""
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        return self.verify(canonical, signature, public_key)

    # ── DID Document ──

    def build_document(self) -> DIDDocument:
        """构建当前身份的 DID Document"""
        return self._reg.build_document()

    def export_document_json(self) -> str:
        """导出 DID Document 为 JSON 字符串"""
        return self._reg.build_document().to_json()

    def export_private_key(self) -> bytes:
        """导出私钥 bytes"""
        return self._reg.export_private_key()

    def export_public_key(self) -> bytes:
        """导出公钥 bytes"""
        return self._reg.export_public_key()

    # ── 导入/导出到 .aid 目录 ──

    AID_DIR_NAMES = {
        "keys": "私钥/公钥存储",
        "docs": "DID Document 导出",
    }

    def save_to_aid_dir(self, aid_dir: Union[str, Path] = "~/.aid") -> dict:
        """将身份保存到 .aid 目录规范

        创建目录结构：
            .aid/
            ├── identity.priv      # 私钥 (32 bytes seed)
            ├── identity.pub       # 公钥 (32 bytes)
            ├── identity.did       # did 字符串
            └── identity.doc.json  # DID Document

        Args:
            aid_dir: .aid 目录路径（默认 ~/.aid）

        Returns:
            { "did": str, "files": [文件路径列表] }
        """
        base = Path(aid_dir).expanduser()
        base.mkdir(parents=True, exist_ok=True)

        priv_file = base / "identity.priv"
        pub_file = base / "identity.pub"
        did_file = base / "identity.did"
        doc_file = base / "identity.doc.json"

        priv_file.write_bytes(self.export_private_key())
        pub_file.write_bytes(self.export_public_key())
        did_file.write_text(self._reg.did)
        doc_file.write_text(self.export_document_json())

        return {
            "did": self._reg.did,
            "files": [str(f) for f in [priv_file, pub_file, did_file, doc_file]],
        }

    def load_from_aid_dir(self, aid_dir: Union[str, Path] = "~/.aid") -> str:
        """从 .aid 目录加载身份

        Args:
            aid_dir: .aid 目录路径

        Returns:
            did 字符串

        Raises:
            FileNotFoundError: identity.priv 不存在
        """
        base = Path(aid_dir).expanduser()
        priv_file = base / "identity.priv"
        if not priv_file.exists():
            raise FileNotFoundError(f"No identity found in {aid_dir}")
        return self.load_private_key(priv_file)
