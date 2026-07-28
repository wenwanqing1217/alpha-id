"""DID 解析器 — 将 did:aid: 解析为 DID Document

解析策略（按优先级）：
1. 本地 .aid/ 目录
2. 已知公钥字节（内存中）
3. Git 仓库 / HTTP（未来）

缓存策略：
- 使用 LRU 驱逐，最大缓存 1000 个 DID Document
- 防止无限增长导致 OOM

用法：
    resolver = DIDResolver()
    doc = resolver.resolve("did:aid:abc123...")
    if doc:
        print(doc.to_json())
"""

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from alpha_id.did import DIDDocument, _b58encode

# LRU 缓存最大容量
_CACHE_MAX_SIZE = 1000
_RESOLVER_CACHE: "OrderedDict[str, DIDDocument]" = OrderedDict()


class DIDResolver:
    """did:aid 方法解析器"""

    def resolve(self, did: str) -> Optional[DIDDocument]:
        """解析 DID → DID Document

        Args:
            did: 完整 DID 字符串（did:aid:...）

        Returns:
            DIDDocument 或 None（未找到）
        """
        if not did.startswith("did:aid:"):
            return None

        # 检查缓存（LRU：移到末尾表示最近使用）
        if did in _RESOLVER_CACHE:
            _RESOLVER_CACHE.move_to_end(did)
            return _RESOLVER_CACHE[did]

        # 1. 尝试本地 .aid/ 目录
        doc = self._resolve_local(did)
        if doc:
            _cache_set(did, doc)
            return doc

        return None

    def resolve_from_public_key(self, public_key_bytes: bytes) -> DIDDocument:
        """从公钥重建 DID Document（无需存储）"""
        did_hash = hashlib.sha256(public_key_bytes).digest()[:16]
        did = f"did:aid:{_b58encode(did_hash)}"
        pub_b58 = _b58encode(public_key_bytes)
        vm_id = f"{did}#key-1"
        doc = DIDDocument(
            id=did,
            verification_method=[
                {
                    "id": vm_id,
                    "type": "Ed25519VerificationKey2018",
                    "controller": did,
                    "publicKeyMultibase": "z" + pub_b58,
                }
            ],
            authentication=[vm_id],
        )
        _cache_set(did, doc)
        return doc

    def resolve_with_key(self, did: str, public_key_hex: str) -> Optional[DIDDocument]:
        """用已知公钥 hex 字符串解析 DID"""
        if not did.startswith("did:aid:"):
            return None
        try:
            pk_bytes = bytes.fromhex(public_key_hex)
        except ValueError:
            return None
        return self.resolve_from_public_key(pk_bytes)

    def _resolve_local(self, did: str) -> Optional[DIDDocument]:
        """从 ~/.aid/ 目录查找"""
        aid_dir = Path.home() / ".aid"
        doc_file = aid_dir / "identity.doc.json"
        did_file = aid_dir / "identity.did"

        if doc_file.exists() and did_file.exists():
            local_did = did_file.read_text().strip()
            if local_did == did:
                try:
                    return DIDDocument.from_json(doc_file.read_text())
                except (json.JSONDecodeError, KeyError):
                    pass
        return None

    @staticmethod
    def clear_cache():
        _RESOLVER_CACHE.clear()

    @staticmethod
    def verify_did(did: str, public_key_bytes: bytes) -> bool:
        """验证公钥是否匹配 DID"""
        from alpha_id.did import DIDRegistry

        return DIDRegistry.did_matches_key(did, public_key_bytes)


def _cache_set(did: str, doc: DIDDocument) -> None:
    """带 LRU 驱逐的缓存插入"""
    if did in _RESOLVER_CACHE:
        # 已存在，移到末尾（最近使用）
        _RESOLVER_CACHE.move_to_end(did)
        _RESOLVER_CACHE[did] = doc
    else:
        # 超过容量时驱逐最旧的条目
        if len(_RESOLVER_CACHE) >= _CACHE_MAX_SIZE:
            _RESOLVER_CACHE.popitem(last=False)
        _RESOLVER_CACHE[did] = doc
