# TERM: DualChain — 双链记忆隔离（私有链加密 + 知识链公开）
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
import logging
import os
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.memory_store import AlphaMemory
from core.settings import settings
from core.storage import StorageBackend

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 加密工具
# ═══════════════════════════════════════════

def _sanitize_alpha_id(alpha_id: str) -> str:
    """安全清洗 alpha_id，防止路径遍历攻击

    - 只允许字母、数字、连字符、下划线（移除冒号，Windows 文件名不允许）
    - 移除路径分隔符和 ../ 序列
    - 限制长度防止缓冲区溢出
    """
    # 只允许安全字符（注意：冒号 : 在 Windows 文件名中非法，必须替换）
    sanitized = re.sub(r'[^a-zA-Z0-9\-_]', '_', alpha_id)
    # 移除任何剩余的路径遍历尝试
    sanitized = sanitized.replace('..', '_')
    # 限制长度
    return sanitized[:128]


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

        # 统一存储后端：SQLite
        if storage is None:
            base = settings.coze_workspace_path or settings.ghost_workspace_path or os.getcwd()
            db_path = os.path.join(base, "assets", "alpha_id.db")
            from core.storage_sqlite import SqliteStorage
            self._private_storage = SqliteStorage(db_path)
            self._knowledge_storage = SqliteStorage(db_path)
        else:
            self._private_storage = storage
            self._knowledge_storage = storage

        # 记录级存储的 collection 名称（避免与旧文档级 key 冲突）
        self._collection_private = _sanitize_alpha_id(f"private_{alpha_id}")
        self._collection_knowledge = _sanitize_alpha_id(f"knowledge_{alpha_id}")
        # 链元数据（document-level，小而少变）
        self._meta_key_private = _sanitize_alpha_id(f"private_{alpha_id}_meta")
        self._meta_key_knowledge = _sanitize_alpha_id(f"knowledge_{alpha_id}_meta")

        self._init_stores()

    def _get_or_create_salt(self) -> bytes:
        """获取或创建用户的加密 salt"""
        base = settings.coze_workspace_path or settings.ghost_workspace_path or os.getcwd()
        safe_id = _sanitize_alpha_id(self.alpha_id)
        salt_path = os.path.join(base, "assets", ".salt_" + safe_id)
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
        """初始化两条链的存储（记录级 collection + 兼容旧文档级数据迁移）"""
        for chain, storage, collection, meta_key in [
            ("private", self._private_storage, self._collection_private, self._meta_key_private),
            ("knowledge", self._knowledge_storage, self._collection_knowledge, self._meta_key_knowledge),
        ]:
            # 确保 chain metadata 存在
            meta = storage.load(meta_key)
            if meta is None:
                # 检查旧文档级数据是否存在（向后兼容迁移）
                old_key = _sanitize_alpha_id(f"{chain}_{self.alpha_id}")
                old_data = storage.load(old_key)
                if old_data and old_data.get("memories"):
                    # 迁移：将旧文档拆分为记录级存储
                    memories = old_data.get("memories", {})
                    for mem_id, mem_record in memories.items():
                        storage.put(collection, mem_id, mem_record)
                    logger.info("已迁移 %d 条记忆从旧文档格式到记录级存储 (%s chain)", len(memories), chain)
                    # 可选：删除旧文档以节省空间
                    # storage.save(old_key, None)  # 某些后端不支持，保留旧数据
                meta = {"created_at": datetime.now().isoformat(), "migrated_from_doc": bool(old_data)}
                storage.save(meta_key, meta)

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

    def _get_storage(self, chain: str):
        storage = self._private_storage if chain == "private" else self._knowledge_storage
        collection = self._collection_private if chain == "private" else self._collection_knowledge
        return storage, collection

    def _save_to_chain(self, chain: str, memory_id: str, record: Dict) -> Dict[str, Any]:
        """写入指定链（记录级存储，O(1) 不加载全文档）"""
        storage, collection = self._get_storage(chain)
        meta_key = self._meta_key_private if chain == "private" else self._meta_key_knowledge

        if chain == "private":
            # 加密内容
            encrypted = _encrypt(record["content"], self._key)
            record["content"] = encrypted["ciphertext"]
            record["nonce"] = encrypted["nonce"]
            record["encrypted"] = True

        # 记录级写入：只写这一条，不加载全文档
        storage.put(collection, memory_id, record)

        # 更新链元数据（小型 document，可接受全量读写）
        meta = storage.load(meta_key) or {}
        meta.setdefault("record_count", 0)
        meta["record_count"] += 1
        meta["last_updated"] = datetime.now().isoformat()
        storage.save(meta_key, meta)

        return {
            "success": True,
            "memory_id": memory_id,
            "chain": chain,
            "encrypted": chain == "private",
            "message": f"记忆已保存至{'私有' if chain == 'private' else '知识'}链",
        }

    # ── 核心读取 ──

    def get(self, memory_id: str, chain: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取单条记忆（自动搜索两条链，记录级 O(1) 查询）"""
        for c in (["private", "knowledge"] if chain is None else [chain]):
            storage, collection = self._get_storage(c)
            record = storage.get(collection, memory_id)
            if record is not None:
                record = dict(record)
                record["_chain"] = c
                if c == "private" and record.get("encrypted"):
                    try:
                        decrypted = _decrypt(
                            {"nonce": record["nonce"], "ciphertext": record["content"]},
                            self._key,
                        )
                        record["content"] = decrypted
                    except Exception as exc:
                        logger.warning("Private chain decryption failed for record %s: %s", record.get("id", "?"), exc)
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
        查询记忆（记录级存储，O(记录数) 而非 O(全文档大小)）。

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
            storage, collection = self._get_storage(c)

            # 记录级列表：只加载符合条件的记录，不加载全文档
            filters = {}
            if category:
                filters["category"] = category
            if max_sensitivity < 100:
                # sensitivity 过滤在客户端做（存储层不支持范围查询）
                pass
            memories = storage.list(collection, filters=filters if filters else None)

            for mem in memories:
                # 敏感度过滤
                if mem.get("sensitivity", 0) > max_sensitivity:
                    continue

                record = dict(mem)
                record["_chain"] = c

                # 解密私有链内容用于搜索
                if c == "private" and mem.get("encrypted"):
                    try:
                        decrypted = _decrypt(
                            {"nonce": mem["nonce"], "ciphertext": mem["content"]},
                            self._key,
                        )
                        record["content"] = decrypted
                    except Exception as exc:
                        logger.warning("Private chain decryption failed during query: %s", exc)
                        record["content"] = "[解密失败]"
                        continue

                # 关键词搜索
                if keyword:
                    kw = keyword.lower()
                    content = record.get("content", "")
                    if isinstance(content, str):
                        content_match = kw in content.lower()
                    else:
                        content_match = kw in str(content).lower()
                    tag_match = kw in " ".join(
                        t if isinstance(t, str) else str(t)
                        for t in record.get("tags", [])
                    ).lower()
                    if not content_match and not tag_match:
                        continue

                results.append(record)

        # 按时间倒序
        results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return results[:limit]

    # ── 迁移操作 ──

    def migrate(self, memory_id: str, target_chain: str) -> Dict[str, Any]:
        """
        将记忆迁移到另一条链（记录级操作）。

        - 迁到私有链：加密内容
        - 迁到知识链：解密内容
        """
        # 找到记忆
        source_chain = None
        record = None
        for c in ["private", "knowledge"]:
            storage, collection = self._get_storage(c)
            rec = storage.get(collection, memory_id)
            if rec is not None:
                source_chain = c
                record = dict(rec)
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
            except Exception as exc:
                logger.error("Chain migration decryption failed for record %s: %s", record.get("id", "?"), exc)
                return {"success": False, "message": "解密失败，无法迁移"}

        # 调整敏感度
        if target_chain == "private":
            record["sensitivity"] = max(record.get("sensitivity", 0), PRIVACY_THRESHOLD)
        else:
            record["sensitivity"] = min(record.get("sensitivity", PRIVACY_THRESHOLD), PRIVACY_THRESHOLD - 1)

        # 从源链删除（记录级）
        src_storage, src_collection = self._get_storage(source_chain)
        src_storage.delete(src_collection, memory_id)

        # 写入目标链（记录级）
        result = self._save_to_chain(target_chain, memory_id, record)
        result["migrated_from"] = source_chain
        return result

    # ── 统计 ──

    def stats(self) -> ChainStats:
        """获取双链统计（记录级计数，不加载全文档）"""
        priv_storage, priv_collection = self._get_storage("private")
        know_storage, know_collection = self._get_storage("knowledge")

        # 优先从元数据读取计数（O(1)）
        priv_meta = priv_storage.load(self._meta_key_private) or {}
        know_meta = know_storage.load(self._meta_key_knowledge) or {}

        private_count = priv_meta.get("record_count")
        knowledge_count = know_meta.get("record_count")

        # 如果元数据不可用，回退到 list 计数（仍然不加载全文档）
        if private_count is None:
            private_count = priv_storage.count(priv_collection)
        if knowledge_count is None:
            knowledge_count = know_storage.count(know_collection)

        total = private_count + knowledge_count

        # 加密比例：只统计私有链（需要逐条检查 encrypted 标记）
        # 对于大量记录，使用 list + filter 而非全文档加载
        encrypted = 0
        if private_count > 0:
            priv_records = priv_storage.list(priv_collection, filters={"encrypted": True})
            encrypted = len(priv_records)
        ratio = encrypted / private_count if private_count > 0 else 1.0

        return ChainStats(
            private_count=private_count,
            knowledge_count=knowledge_count,
            total_count=total,
            private_encrypted_ratio=ratio,
        )

    # ── 删除 ──

    def delete(self, memory_id: str) -> Dict[str, Any]:
        """从任一链删除记忆（记录级 O(1)）"""
        for c in ["private", "knowledge"]:
            storage, collection = self._get_storage(c)
            existing = storage.get(collection, memory_id)
            if existing is not None:
                storage.delete(collection, memory_id)
                # 更新链元数据
                meta_key = self._meta_key_private if c == "private" else self._meta_key_knowledge
                meta = storage.load(meta_key) or {}
                meta.setdefault("record_count", 1)
                meta["record_count"] = max(0, meta["record_count"] - 1)
                meta["last_updated"] = datetime.now().isoformat()
                storage.save(meta_key, meta)
                return {"success": True, "message": f"已从{'私有' if c == 'private' else '知识'}链删除"}
        return {"success": False, "message": "记忆不存在"}

    def clear_chain(self, chain: str) -> Dict[str, Any]:
        """清空指定链（记录级批量删除）"""
        storage, collection = self._get_storage(chain)
        meta_key = self._meta_key_private if chain == "private" else self._meta_key_knowledge

        # 列出所有记录并逐条删除（兼容所有 StorageBackend 实现）
        all_records = storage.list(collection)
        for rec in all_records:
            mem_id = rec.get("memory_id")
            if mem_id:
                storage.delete(collection, mem_id)

        # 重置元数据
        meta = {"created_at": datetime.now().isoformat(), "record_count": 0}
        storage.save(meta_key, meta)

        return {"success": True, "message": f"{'私有' if chain == 'private' else '知识'}链已清空"}

    # ── 批量操作 ──

    def list_chain(self, chain: str, limit: int = 50) -> List[Dict[str, Any]]:
        """列出指定链的记忆摘要（不解密私有链内容）"""
        storage, collection = self._get_storage(chain)
        records = storage.list(collection)
        results = []
        for rec in records[:limit]:
            record = dict(rec)
            record["_chain"] = chain
            if chain == "private" and rec.get("encrypted"):
                record["content"] = "[已加密]"
            results.append(record)
        results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return results
