"""
双链记忆隔离 —— 私有链 / 知识链

核心设计：
  - 私有链 (Private Chain): sensitivity >= 70，加密存储，本地永不上传
  - 知识链 (Knowledge Chain): sensitivity < 70，可搜索、可共享
  - 记忆写入时按敏感度自动分链
  - 支持链间迁移（降级到私有链 / 升级到知识链）
  - 加密使用 AES-256-GCM，密钥从用户 DID 派生

依赖: cryptography (已在 alpha_id.crypto 中使用)
"""

import hashlib
import hmac
import json
import os
import secrets
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.memory_store import AlphaMemory, MemoryStore
from core.storage import JsonStorage, StorageBackend


# ═══════════════════════════════════════════
# 加密工具
# ═══════════════════════════════════════════

def _derive_key(did: str, salt: bytes) -> bytes:
    """从 DID 派生 256 位加密密钥（PBKDF2-HMAC-SHA256）"""
    return hashlib.pbkdf2_hmac("sha256", did.encode("utf-8"), salt, iterations=100_000)


def _encrypt(plaintext: str, key: bytes) -> Dict[str, str]:
    """AES-256-GCM 加密（纯 Python 实现基于 cryptography 库）"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return {
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
    }


def _decrypt(cipher_data: Dict[str, str], key: bytes) -> str:
    """AES-256-GCM 解密"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = bytes.fromhex(cipher_data["nonce"])
    ciphertext = bytes.fromhex(cipher_data["ciphertext"])
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


# ═══════════════════════════════════════════
# 双链管理器
# ═══════════════════════════════════════════

# 敏感度阈值：>= 此值进入私有链
PRIVACY_THRESHOLD = 70


@dataclass
class ChainStats:
    """双链统计"""
    private_count: int = 0
    knowledge_count: int = 0
    total_count: int = 0
    private_encrypted_ratio: float = 1.0  # 私有链加密比例


class DualChainManager:
    """
    双链记忆隔离管理器

    每个 Alpha-ID 拥有两条独立的记忆链：
      - private: 高敏感记忆，加密存储
      - knowledge: 低敏感记忆，明文存储可搜索

    使用方式：
        manager = DualChainManager(alpha_id="did:aid:xxxx")
        manager.save("我的密码是123", sensitivity=90)  → 自动进入私有链
        manager.save("今天天气不错", sensitivity=10)   → 自动进入知识链
        manager.query(chain="private", keyword="密码")  → 搜索私有链
    """

    def __init__(self, alpha_id: str, storage: Optional[StorageBackend] = None):
        self.alpha_id = alpha_id
        self._salt = self._get_or_create_salt()
        self._key = _derive_key(alpha_id, self._salt)

        # 存储路径
        if storage is None:
            base = os.getenv("COZE_WORKSPACE_PATH", os.getcwd())
            priv_path = os.path.join(base, "assets", f"private_chain_{alpha_id.replace(':', '_')}.json")
            know_path = os.path.join(base, "assets", f"knowledge_chain_{alpha_id.replace(':', '_')}.json")
            self._private_storage = JsonStorage(priv_path)
            self._knowledge_storage = JsonStorage(know_path)
        else:
            # 使用传入的存储后端（测试用）
            self._private_storage = storage
            self._knowledge_storage = storage

        self._init_stores()

    def _get_or_create_salt(self) -> bytes:
        """获取或创建用户的加密 salt"""
        base = os.getenv("COZE_WORKSPACE_PATH", os.getcwd())
        salt_path = os.path.join(base, "assets", ".salt_" + self.alpha_id.replace(":", "_"))
        try:
            with open(salt_path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            salt = secrets.token_bytes(16)
            os.makedirs(os.path.dirname(salt_path), exist_ok=True)
            with open(salt_path, "wb") as f:
                f.write(salt)
            return salt

    def _init_stores(self):
        """初始化两条链的存储"""
        for store in [self._private_storage, self._knowledge_storage]:
            data = store.load(self.alpha_id)
            if data is None:
                store.save(self.alpha_id, {"memories": {}, "chain_meta": {"created_at": datetime.now().isoformat()}})

    # ── 核心写入 ──

    def save(
        self,
        content: str,
        category: str = "general",
        sensitivity: int = 0,
        source: str = "self",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        保存记忆 —— 按敏感度自动分链。

        sensitivity >= 70 → 私有链（加密）
        sensitivity < 70  → 知识链（明文）
        """
        sensitivity = max(0, min(100, sensitivity))
        memory = AlphaMemory(
            alpha_id=self.alpha_id,
            content=content,
            category=category,
            sensitivity=sensitivity,
            source=source,
            tags=tags or [],
        )
        record = asdict(memory)

        if sensitivity >= PRIVACY_THRESHOLD:
            return self._save_to_chain("private", memory.memory_id, record)
        else:
            return self._save_to_chain("knowledge", memory.memory_id, record)

    def _save_to_chain(self, chain: str, memory_id: str, record: Dict) -> Dict[str, Any]:
        """写入指定链"""
        storage = self._private_storage if chain == "private" else self._knowledge_storage
        data = storage.load(self.alpha_id) or {"memories": {}, "chain_meta": {}}

        if chain == "private":
            # 加密内容
            encrypted = _encrypt(record["content"], self._key)
            record["content"] = encrypted["ciphertext"]
            record["nonce"] = encrypted["nonce"]
            record["encrypted"] = True

        data["memories"][memory_id] = record
        storage.save(self.alpha_id, data)

        return {
            "success": True,
            "memory_id": memory_id,
            "chain": chain,
            "encrypted": chain == "private",
            "message": f"记忆已保存至{'私有' if chain == 'private' else '知识'}链",
        }

    # ── 核心读取 ──

    def get(self, memory_id: str, chain: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取单条记忆（自动搜索两条链）"""
        for c in (["private", "knowledge"] if chain is None else [chain]):
            storage = self._private_storage if c == "private" else self._knowledge_storage
            data = storage.load(self.alpha_id) or {}
            memories = data.get("memories", {})
            if memory_id in memories:
                record = dict(memories[memory_id])
                record["_chain"] = c
                if c == "private" and record.get("encrypted"):
                    try:
                        decrypted = _decrypt(
                            {"nonce": record["nonce"], "ciphertext": record["content"]},
                            self._key,
                        )
                        record["content"] = decrypted
                    except Exception:
                        record["content"] = "[解密失败]"
                return record
        return None

    def query(
        self,
        chain: str = "all",
        keyword: str = "",
        category: str = "",
        max_sensitivity: int = 100,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        查询记忆。

        Args:
            chain: "private" / "knowledge" / "all"
            keyword: 关键词搜索
            category: 分类过滤
            max_sensitivity: 最大敏感度
            limit: 最大返回数
        """
        results = []
        chains = ["private", "knowledge"] if chain == "all" else [chain]

        for c in chains:
            storage = self._private_storage if c == "private" else self._knowledge_storage
            data = storage.load(self.alpha_id) or {}
            memories = data.get("memories", {})

            for mid, mem in memories.items():
                # 敏感度过滤
                if mem.get("sensitivity", 0) > max_sensitivity:
                    continue
                # 分类过滤
                if category and mem.get("category") != category:
                    continue

                record = dict(mem)
                record["memory_id"] = mid
                record["_chain"] = c

                # 解密私有链内容用于搜索
                if c == "private" and mem.get("encrypted"):
                    try:
                        decrypted = _decrypt(
                            {"nonce": mem["nonce"], "ciphertext": mem["content"]},
                            self._key,
                        )
                        record["content"] = decrypted
                    except Exception:
                        record["content"] = "[解密失败]"
                        continue  # 解密失败则跳过

                # 关键词搜索
                if keyword:
                    kw = keyword.lower()
                    content_match = kw in record.get("content", "").lower()
                    tag_match = kw in " ".join(record.get("tags", [])).lower()
                    if not content_match and not tag_match:
                        continue

                results.append(record)

        # 按时间倒序
        results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return results[:limit]

    # ── 迁移操作 ──

    def migrate(self, memory_id: str, target_chain: str) -> Dict[str, Any]:
        """
        将记忆迁移到另一条链。

        - 迁到私有链：加密内容
        - 迁到知识链：解密内容
        """
        # 找到记忆
        source_chain = None
        record = None
        for c in ["private", "knowledge"]:
            storage = self._private_storage if c == "private" else self._knowledge_storage
            data = storage.load(self.alpha_id) or {}
            memories = data.get("memories", {})
            if memory_id in memories:
                source_chain = c
                record = dict(memories[memory_id])
                break

        if record is None:
            return {"success": False, "message": "记忆不存在"}

        if source_chain == target_chain:
            return {"success": False, "message": "已在目标链"}

        # 解密（如果在私有链）
        if source_chain == "private" and record.get("encrypted"):
            try:
                decrypted = _decrypt(
                    {"nonce": record["nonce"], "ciphertext": record["content"]},
                    self._key,
                )
                record["content"] = decrypted
                record.pop("encrypted", None)
                record.pop("nonce", None)
            except Exception:
                return {"success": False, "message": "解密失败，无法迁移"}

        # 调整敏感度
        if target_chain == "private":
            record["sensitivity"] = max(record.get("sensitivity", 0), PRIVACY_THRESHOLD)
        else:
            record["sensitivity"] = min(record.get("sensitivity", PRIVACY_THRESHOLD), PRIVACY_THRESHOLD - 1)

        # 从源链删除
        src_storage = self._private_storage if source_chain == "private" else self._knowledge_storage
        src_data = src_storage.load(self.alpha_id) or {}
        src_memories = src_data.get("memories", {})
        if memory_id in src_memories:
            del src_memories[memory_id]
            src_storage.save(self.alpha_id, {**src_data, "memories": src_memories})

        # 写入目标链
        result = self._save_to_chain(target_chain, memory_id, record)
        result["migrated_from"] = source_chain
        return result

    # ── 统计 ──

    def stats(self) -> ChainStats:
        """获取双链统计"""
        priv_data = self._private_storage.load(self.alpha_id) or {}
        know_data = self._knowledge_storage.load(self.alpha_id) or {}
        priv_memories = priv_data.get("memories", {})
        know_memories = know_data.get("memories", {})

        private_count = len(priv_memories)
        knowledge_count = len(know_memories)
        total = private_count + knowledge_count

        encrypted = sum(1 for m in priv_memories.values() if m.get("encrypted", False))
        ratio = encrypted / private_count if private_count > 0 else 1.0

        return ChainStats(
            private_count=private_count,
            knowledge_count=knowledge_count,
            total_count=total,
            private_encrypted_ratio=ratio,
        )

    # ── 删除 ──

    def delete(self, memory_id: str) -> Dict[str, Any]:
        """从任一链删除记忆"""
        for c in ["private", "knowledge"]:
            storage = self._private_storage if c == "private" else self._knowledge_storage
            data = storage.load(self.alpha_id) or {}
            memories = data.get("memories", {})
            if memory_id in memories:
                del memories[memory_id]
                storage.save(self.alpha_id, {**data, "memories": memories})
                return {"success": True, "message": f"已从{'私有' if c == 'private' else '知识'}链删除"}
        return {"success": False, "message": "记忆不存在"}

    def clear_chain(self, chain: str) -> Dict[str, Any]:
        """清空指定链"""
        storage = self._private_storage if chain == "private" else self._knowledge_storage
        data = storage.load(self.alpha_id) or {}
        data["memories"] = {}
        storage.save(self.alpha_id, data)
        return {"success": True, "message": f"{'私有' if chain == 'private' else '知识'}链已清空"}

    # ── 批量操作 ──

    def list_chain(self, chain: str, limit: int = 50) -> List[Dict[str, Any]]:
        """列出指定链的所有记忆（不解密私有链摘要）"""
        storage = self._private_storage if chain == "private" else self._knowledge_storage
        data = storage.load(self.alpha_id) or {}
        memories = data.get("memories", {})
        results = []
        for mid, mem in list(memories.items())[:limit]:
            record = dict(mem)
            record["memory_id"] = mid
            record["_chain"] = chain
            if chain == "private" and mem.get("encrypted"):
                record["content"] = "[已加密]"
            results.append(record)
        results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return results
