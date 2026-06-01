"""
P3-1: Proof of Execution（执行证明）

每次技能执行生成一个可验证的 Ed25519 签名记录。
PoE 链可以串联：A 调用 B 的技能 → B 的 PoE 包含 A 的 PoE ID。

用法：
    from alpha_id.poe import ProofOfExecution, PoEStore, PoEClient

    # 生成
    signer = AIDSigner(); signer.generate()
    poe = PoEClient(signer).generate(
        skill_name="greet",
        skill_version="0.1.0",
        skill_content_hash="abc...",
        executor_did=signer.did,
        author_did="did:aid:author",
        params={"name": "World"},
        output="hello World",
        success=True,
        duration_ms=42,
    )
    print(f"PoE ID: {poe.poe_id}")

    # 验证
    assert poe.verify(signer.public_key)
"""

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


POE_VERSION = "1.0"


@dataclass
class ProofOfExecution:
    """执行证明——每次技能执行生成的可验证 Ed25519 签名记录

    核心字段：
        poe_id:         证明唯一 ID（内容哈希的 hex[:16]）
        skill_name:     技能名称
        skill_version:  技能版本
        skill_content_hash:  技能内容的 SHA256
        executor_did:   执行者的 DID
        author_did:     技能作者的 DID
        timestamp:      Unix 执行时间戳
        params_hash:    参数 JSON 的 SHA256
        output_hash:    输出字符串的 SHA256
        success:        是否成功
        duration_ms:    耗时毫秒
        parent_poe_id:  父 PoE ID（链式调用）
        signature:      executor 对 payload 的 Ed25519 签名（hex）
        poe_version:    PoE 格式版本
    """

    skill_name: str
    skill_version: str
    skill_content_hash: str
    executor_did: str
    author_did: str
    timestamp: float
    params_hash: str
    output_hash: str
    success: bool
    duration_ms: int
    parent_poe_id: str = ""
    poe_id: str = ""
    signature: str = ""
    poe_version: str = POE_VERSION

    def _payload(self) -> bytes:
        """签名的规范有效载荷（不含 poe_id 和 signature 本身）"""
        obj = {
            "poe_version": self.poe_version,
            "skill_name": self.skill_name,
            "skill_version": self.skill_version,
            "skill_content_hash": self.skill_content_hash,
            "executor_did": self.executor_did,
            "author_did": self.author_did,
            "timestamp": self.timestamp,
            "params_hash": self.params_hash,
            "output_hash": self.output_hash,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "parent_poe_id": self.parent_poe_id,
        }
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

    def compute_poe_id(self) -> str:
        """计算 PoE ID（payload 的 SHA256 hex[:16]）"""
        return hashlib.sha256(self._payload()).hexdigest()[:16]

    def sign(self, signer) -> str:
        """用执行者的 AIDSigner 签名

        使用 cryptography 库进行 Ed25519 签名（绕过纯 Python 实现的已知 bug）。

        Args:
            signer: AIDSigner 实例（必须已有身份）

        Returns:
            poe_id 字符串
        """
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        priv_key = Ed25519PrivateKey.from_private_bytes(signer.export_private_key())
        self.poe_id = self.compute_poe_id()
        self.signature = priv_key.sign(self._payload()).hex()
        return self.poe_id

    def verify(self, public_key: bytes) -> bool:
        """验证签名

        使用 cryptography 库进行 Ed25519 验签（纯 Python 实现有已知 bug）。

        Args:
            public_key: 执行者的 Ed25519 公钥

        Returns:
            True 验证通过
        """
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        try:
            pub = Ed25519PublicKey.from_public_bytes(public_key)
            pub.verify(bytes.fromhex(self.signature), self._payload())
            logger.debug("PoE verify OK: %s", self.poe_id)
            return True
        except Exception:
            logger.debug("PoE verify FAILED: %s", self.poe_id)
            return False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProofOfExecution":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, text: str) -> "ProofOfExecution":
        return cls.from_dict(json.loads(text))

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def summary(self) -> str:
        status = "✅" if self.success else "❌"
        return (
            f"{status} PoE {self.poe_id} | "
            f"{self.skill_name}@{self.skill_version} "
            f"by {self.executor_did[:16]}... "
            f"← author {self.author_did[:16]}... "
            f"({self.duration_ms}ms)"
        )


# ═══════════════════════════════════════════
# PoE 持久化存储
# ═══════════════════════════════════════════


class PoEStore:
    """PoE 记录存储——按日期分片的 JSONL 持久化

    目录结构：
        {storage_dir}/
            poes/
                2025-07-14.jsonl
                ...
    """

    def __init__(self, storage_dir: str):
        self._base = Path(storage_dir).expanduser()
        self._poes_dir = self._base / "poes"
        self._poes_dir.mkdir(parents=True, exist_ok=True)

    def _today_file(self) -> Path:
        return self._poes_dir / f"{time.strftime('%Y-%m-%d')}.jsonl"

    def record(self, poe: ProofOfExecution):
        """保存一条 PoE 记录"""
        path = self._today_file()
        line = json.dumps(poe.to_dict(), ensure_ascii=False, sort_keys=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        logger.info("PoE recorded: %s -> %s", poe.poe_id, path)

    def get(self, poe_id: str) -> Optional[ProofOfExecution]:
        """按 poe_id 查找"""
        for poe in self._iter_all():
            if poe.poe_id == poe_id:
                return poe
        return None

    def list_for_skill(self, skill_name: str, limit: int = 50) -> List[ProofOfExecution]:
        """列出某个技能的所有执行证明"""
        results = []
        for poe in self._iter_all():
            if poe.skill_name == skill_name:
                results.append(poe)
                if len(results) >= limit:
                    break
        logger.debug("list_for_skill(%s): %d results", skill_name, len(results))
        return results

    def list_for_executor(self, executor_did: str, limit: int = 50) -> List[ProofOfExecution]:
        """列出某个执行者的所有执行证明"""
        results = []
        for poe in self._iter_all():
            if poe.executor_did == executor_did:
                results.append(poe)
                if len(results) >= limit:
                    break
        logger.debug("list_for_executor(%s): %d results", executor_did[:16], len(results))
        return results

    def list_all(self, limit: int = 100) -> List[ProofOfExecution]:
        """列出最近的执行证明"""
        results = []
        for poe in self._iter_all():
            results.append(poe)
            if len(results) >= limit:
                break
        logger.debug("list_all: %d results", len(results))
        return results

    def count(self) -> int:
        """总记录数"""
        return sum(1 for _ in self._iter_all())

    def _iter_all(self):
        """逆序遍历所有 JSONL 文件（最新的优先）"""
        files = sorted(self._poes_dir.glob("*.jsonl"), reverse=True)
        for path in files:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield ProofOfExecution.from_json(line)


# ═══════════════════════════════════════════
# PoE 生成器
# ═══════════════════════════════════════════


class PoEClient:
    """PoE 生成器——用执行者的身份签名每次执行"""

    def __init__(self, signer, store: Optional[PoEStore] = None, parent_poe_id: str = ""):
        """
        Args:
            signer: AIDSigner 实例（执行者的身份，用于签名 PoE）
            store: 可选 PoEStore，如果提供则自动持久化
            parent_poe_id: 父 PoE ID（链式调用时传递）
        """
        self._signer = signer
        self._store = store
        self._parent_poe_id = parent_poe_id

    def generate(
        self,
        skill_name: str,
        skill_version: str,
        skill_content_hash: str,
        executor_did: str,
        author_did: str,
        params: dict,
        output: str,
        success: bool,
        duration_ms: int,
    ) -> ProofOfExecution:
        """生成签名后的 PoE

        Args:
            skill_name: 技能名称
            skill_version: 技能版本
            skill_content_hash: 技能内容 SHA256
            executor_did: 执行者 DID
            author_did: 技能作者 DID
            params: 参数字典
            output: 执行输出文本
            success: 是否成功
            duration_ms: 耗时毫秒

        Returns:
            已签名的 ProofOfExecution
        """
        params_hash = hashlib.sha256(json.dumps(params, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        output_hash = hashlib.sha256(output.encode("utf-8")).hexdigest()

        poe = ProofOfExecution(
            skill_name=skill_name,
            skill_version=skill_version,
            skill_content_hash=skill_content_hash,
            executor_did=executor_did,
            author_did=author_did,
            timestamp=time.time(),
            params_hash=params_hash,
            output_hash=output_hash,
            success=success,
            duration_ms=duration_ms,
            parent_poe_id=self._parent_poe_id,
        )
        poe.sign(self._signer)

        if self._store:
            self._store.record(poe)

        logger.info("PoE generated: %s | %s@%s | %s", poe.poe_id, skill_name, skill_version, executor_did)
        return poe

    def with_chain(self, parent_poe_id: str) -> "PoEClient":
        """创建子 PoEClient（链式调用时使用）"""
        return PoEClient(self._signer, store=self._store, parent_poe_id=parent_poe_id)
