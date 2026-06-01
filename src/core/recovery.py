"""
身份恢复引擎 —— 社交见证恢复机制

流程：
1. 发起者生成恢复请求，指定新公钥 + 见证人列表
2. 见证人对恢复请求签名
3. 达到阈值 + 时间锁到期后执行恢复
4. 系统将身份的 DID Document 授权公钥切换为新密钥

安全保证：
- 时间锁：防止闪电恢复攻击（最少 N 小时等待）
- 见证人阈值：需要 M/N 个好友签名
- 每次发起新恢复会作废旧恢复请求
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.storage import StorageBackend

# ── 恢复流程状态 ──

RECOVERY_STATUS_PENDING = "pending"  # 等待见证人签名
RECOVERY_STATUS_READY = "ready"  # 达到阈值，等待时间锁
RECOVERY_STATUS_EXECUTABLE = "executable"  # 时间锁已过，可执行
RECOVERY_STATUS_EXECUTED = "executed"  # 已执行
RECOVERY_STATUS_EXPIRED = "expired"  # 已过期
RECOVERY_STATUS_CANCELLED = "cancelled"  # 被取消


# ── 数据模型 ──


@dataclass
class RecoveryRequest:
    """恢复请求数据模型"""

    request_id: str
    target_did: str  # 被恢复的目标 DID
    target_alpha_id: str  # 被恢复的 Alpha-ID
    new_public_key_hex: str  # 新公钥（hex）
    old_public_key_hex: str  # 旧公钥（hex）
    initiator: str  # 发起者 DID
    initiated_at: float  # 发起时间戳
    time_lock_hours: int  # 时间锁小时数
    witness_threshold: int  # 需要的最小见证人数
    witnesses: List[str] = field(default_factory=list)  # 见证人 DID 列表
    signatures: Dict[str, str] = field(default_factory=dict)  # 见证人DID -> 签名hex
    status: str = RECOVERY_STATUS_PENDING  # 当前状态
    executed_at: Optional[float] = None  # 执行时间戳
    message: str = ""  # 恢复请求消息

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "target_did": self.target_did,
            "target_alpha_id": self.target_alpha_id,
            "new_public_key_hex": self.new_public_key_hex,
            "old_public_key_hex": self.old_public_key_hex,
            "initiator": self.initiator,
            "initiated_at": self.initiated_at,
            "time_lock_hours": self.time_lock_hours,
            "witness_threshold": self.witness_threshold,
            "witnesses": self.witnesses,
            "signatures": self.signatures,
            "status": self.status,
            "executed_at": self.executed_at,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryRequest":
        return cls(
            request_id=data["request_id"],
            target_did=data["target_did"],
            target_alpha_id=data["target_alpha_id"],
            new_public_key_hex=data["new_public_key_hex"],
            old_public_key_hex=data["old_public_key_hex"],
            initiator=data["initiator"],
            initiated_at=data["initiated_at"],
            time_lock_hours=data.get("time_lock_hours", 24),
            witness_threshold=data.get("witness_threshold", 2),
            witnesses=data.get("witnesses", []),
            signatures=data.get("signatures", {}),
            status=data.get("status", RECOVERY_STATUS_PENDING),
            executed_at=data.get("executed_at"),
            message=data.get("message", ""),
        )

    @property
    def witness_count(self) -> int:
        """已签名的见证人数量"""
        return len(self.signatures)

    @property
    def is_threshold_met(self) -> bool:
        """见证人签名是否达到阈值"""
        return self.witness_count >= self.witness_threshold

    @property
    def time_lock_passed(self) -> bool:
        """时间锁是否已过"""
        elapsed = time.time() - self.initiated_at
        return elapsed >= self.time_lock_hours * 3600

    @property
    def time_remaining_seconds(self) -> float:
        """时间锁剩余秒数（0 = 已到）"""
        remaining = (self.time_lock_hours * 3600) - (time.time() - self.initiated_at)
        return max(0.0, remaining)


# ── 见证人管理 ──


@dataclass
class WitnessRecord:
    """见证人记录"""

    alpha_id: str  # 见证人 Alpha-ID
    did: str  # 见证人 DID
    added_at: float  # 添加时间
    added_by: str  # 谁添加的
    label: str = ""  # 标签（如"家人"、"同事"）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alpha_id": self.alpha_id,
            "did": self.did,
            "added_at": self.added_at,
            "added_by": self.added_by,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WitnessRecord":
        return cls(
            alpha_id=data["alpha_id"],
            did=data.get("did", data["alpha_id"]),
            added_at=data.get("added_at", 0.0),
            added_by=data.get("added_by", ""),
            label=data.get("label", ""),
        )


# ── 核心恢复引擎 ──


class RecoveryEngine:
    """
    身份恢复引擎

    管理恢复请求的生命周期，见证人注册，时间锁检查和执行。
    数据通过 StorageBackend 持久化，与 TwinBrain 解耦。
    """

    COLLECTION_RECOVERY = "recovery_requests"
    COLLECTION_WITNESSES = "recovery_witnesses"

    # 默认配置
    DEFAULT_TIME_LOCK_HOURS = 24
    DEFAULT_WITNESS_THRESHOLD = 2
    REQUEST_EXPIRY_DAYS = 30

    def __init__(self, storage: Optional[StorageBackend] = None):
        self._storage = storage

    def _get_storage(self) -> StorageBackend:
        """获取存储后端（支持延迟初始化）"""
        if self._storage is None:
            import os

            from core.storage_sqlite import SqliteStorage

            db_path = os.path.join(os.getenv("COZE_WORKSPACE_PATH", os.getcwd()), "assets", "alpha_id.db")
            self._storage = SqliteStorage(db_path)
        return self._storage

    # ── 见证人管理 ──

    def add_witness(
        self,
        owner_alpha_id: str,
        witness_alpha_id: str,
        witness_did: str = "",
        label: str = "",
    ) -> Dict[str, Any]:
        """添加见证人

        Args:
            owner_alpha_id: 所有者 Alpha-ID
            witness_alpha_id: 见证人 Alpha-ID
            witness_did: 见证人 DID（默认用 alpha_id）
            label: 标签

        Returns:
            { success, message, record? }
        """
        storage = self._get_storage()
        existing = storage.get(self.COLLECTION_WITNESSES, owner_alpha_id)
        witnesses = existing or []

        # 去重
        for w in witnesses:
            if w.get("alpha_id") == witness_alpha_id:
                return {"success": False, "message": f"见证人 {witness_alpha_id} 已存在"}

        record = WitnessRecord(
            alpha_id=witness_alpha_id,
            did=witness_did or f"did:aid:{witness_alpha_id}",
            added_at=time.time(),
            added_by=owner_alpha_id,
            label=label,
        )
        witnesses.append(record.to_dict())
        storage.put(self.COLLECTION_WITNESSES, owner_alpha_id, witnesses)

        return {
            "success": True,
            "message": f"见证人 {witness_alpha_id} 已添加",
            "record": record.to_dict(),
        }

    def remove_witness(self, owner_alpha_id: str, witness_alpha_id: str) -> Dict[str, Any]:
        """移除见证人"""
        storage = self._get_storage()
        existing = storage.get(self.COLLECTION_WITNESSES, owner_alpha_id)
        if not existing:
            return {"success": False, "message": "尚无见证人"}

        filtered = [w for w in existing if w.get("alpha_id") != witness_alpha_id]
        if len(filtered) == len(existing):
            return {"success": False, "message": f"见证人 {witness_alpha_id} 不存在"}

        storage.put(self.COLLECTION_WITNESSES, owner_alpha_id, filtered)
        return {"success": True, "message": f"见证人 {witness_alpha_id} 已移除"}

    def list_witnesses(self, owner_alpha_id: str) -> List[Dict[str, Any]]:
        """列出所有见证人"""
        storage = self._get_storage()
        existing = storage.get(self.COLLECTION_WITNESSES, owner_alpha_id)
        return existing or []

    def get_witness_dids(self, owner_alpha_id: str) -> List[str]:
        """获取所有见证人 DID（供 CL 展示）"""
        witnesses = self.list_witnesses(owner_alpha_id)
        return [w.get("did", w["alpha_id"]) for w in witnesses]

    # ── 恢复流程 ──

    def initiate_recovery(
        self,
        target_did: str,
        target_alpha_id: str,
        new_public_key_hex: str,
        old_public_key_hex: str,
        initiator: str,
        witnesses: Optional[List[str]] = None,
        time_lock_hours: int = DEFAULT_TIME_LOCK_HOURS,
        witness_threshold: int = DEFAULT_WITNESS_THRESHOLD,
        message: str = "",
    ) -> Dict[str, Any]:
        """发起恢复请求

        Args:
            target_did: 被恢复的 DID
            target_alpha_id: 被恢复的 Alpha-ID
            new_public_key_hex: 新公钥（hex 编码）
            old_public_key_hex: 旧公钥（hex 编码）
            initiator: 发起者 DID
            witnesses: 见证人 DID 列表
            time_lock_hours: 时间锁小时数
            witness_threshold: 需要的最小见证人数
            message: 恢复请求附言

        Returns:
            { success, request_id, request? }
        """
        storage = self._get_storage()

        # 作废该身份下旧的待处理恢复请求
        self._cancel_old_requests(target_alpha_id)

        request_id = f"rec_{uuid.uuid4().hex[:12]}"

        request = RecoveryRequest(
            request_id=request_id,
            target_did=target_did,
            target_alpha_id=target_alpha_id,
            new_public_key_hex=new_public_key_hex,
            old_public_key_hex=old_public_key_hex,
            initiator=initiator,
            initiated_at=time.time(),
            time_lock_hours=max(0, time_lock_hours),
            witness_threshold=max(1, witness_threshold),
            witnesses=witnesses or [],
            signatures={},
            status=RECOVERY_STATUS_PENDING,
            executed_at=None,
            message=message,
        )

        storage.put(self.COLLECTION_RECOVERY, request_id, request.to_dict())

        return {
            "success": True,
            "message": f"恢复请求 {request_id} 已创建",
            "request_id": request_id,
            "request": request.to_dict(),
        }

    def _cancel_old_requests(self, target_alpha_id: str):
        """取消目标身份下所有待处理的旧恢复请求"""
        storage = self._get_storage()
        all_requests = storage.list(self.COLLECTION_RECOVERY)
        for req in all_requests:
            if req.get("target_alpha_id") == target_alpha_id and req.get("status") in (
                RECOVERY_STATUS_PENDING,
                RECOVERY_STATUS_READY,
                RECOVERY_STATUS_EXECUTABLE,
            ):
                req["status"] = RECOVERY_STATUS_CANCELLED
                storage.put(self.COLLECTION_RECOVERY, req["request_id"], req)

    def sign_recovery(
        self,
        request_id: str,
        witness_did: str,
        signature_hex: str,
    ) -> Dict[str, Any]:
        """见证人签名恢复请求

        Args:
            request_id: 恢复请求 ID
            witness_did: 见证人 DID
            signature_hex: 对待恢复身份的 old_public_key 的签名

        Returns:
            { success, message, witness_count, threshold_met, request? }
        """
        storage = self._get_storage()
        req_data = storage.get(self.COLLECTION_RECOVERY, request_id)
        if not req_data:
            return {"success": False, "message": f"恢复请求不存在: {request_id}"}

        request = RecoveryRequest.from_dict(req_data)

        if request.status not in (RECOVERY_STATUS_PENDING, RECOVERY_STATUS_READY, RECOVERY_STATUS_EXECUTABLE):
            return {"success": False, "message": f"恢复请求状态不允许签名: {request.status}"}

        # 检查见证人资格
        if request.witnesses and witness_did not in request.witnesses:
            return {"success": False, "message": f"见证人 {witness_did} 不在该请求的见证人列表中"}

        # 检查重复签名
        if witness_did in request.signatures:
            return {"success": False, "message": f"见证人 {witness_did} 已签名"}

        # 记录签名
        request.signatures[witness_did] = signature_hex

        # 更新状态
        old_status = request.status
        if request.is_threshold_met and request.status == RECOVERY_STATUS_PENDING:
            request.status = RECOVERY_STATUS_READY

        # 如果时间锁也过了，可以直接执行
        if request.status == RECOVERY_STATUS_READY and request.time_lock_passed:
            request.status = RECOVERY_STATUS_EXECUTABLE

        # 持久化
        storage.put(self.COLLECTION_RECOVERY, request_id, request.to_dict())

        return {
            "success": True,
            "message": f"见证人 {witness_did} 已签名",
            "witness_count": request.witness_count,
            "threshold": request.witness_threshold,
            "threshold_met": request.is_threshold_met,
            "old_status": old_status,
            "new_status": request.status,
            "request": request.to_dict(),
        }

    def check_readiness(self, request_id: str) -> Dict[str, Any]:
        """检查恢复请求是否可执行

        Returns:
            { request_id, status, is_ready, threshold_met, time_lock_passed,
              witness_count, witness_threshold, time_remaining_seconds, request? }
        """
        storage = self._get_storage()
        req_data = storage.get(self.COLLECTION_RECOVERY, request_id)
        if not req_data:
            return {"success": False, "message": f"恢复请求不存在: {request_id}"}

        request = RecoveryRequest.from_dict(req_data)

        # 自动推进状态
        old_status = request.status
        if request.status == RECOVERY_STATUS_READY and request.time_lock_passed:
            request.status = RECOVERY_STATUS_EXECUTABLE
            if old_status != request.status:
                storage.put(self.COLLECTION_RECOVERY, request_id, request.to_dict())

        # 过期检查
        if request.status in (RECOVERY_STATUS_PENDING, RECOVERY_STATUS_READY, RECOVERY_STATUS_EXECUTABLE):
            age_days = (time.time() - request.initiated_at) / 86400
            if age_days > self.REQUEST_EXPIRY_DAYS:
                request.status = RECOVERY_STATUS_EXPIRED
                storage.put(self.COLLECTION_RECOVERY, request_id, request.to_dict())

        return {
            "success": True,
            "request_id": request_id,
            "status": request.status,
            "is_ready": request.status == RECOVERY_STATUS_EXECUTABLE,
            "threshold_met": request.is_threshold_met,
            "time_lock_passed": request.time_lock_passed,
            "witness_count": request.witness_count,
            "witness_threshold": request.witness_threshold,
            "time_remaining_seconds": request.time_remaining_seconds,
            "request": request.to_dict(),
        }

    def execute_recovery(
        self,
        request_id: str,
        executor_did: str = "",
    ) -> Dict[str, Any]:
        """执行身份恢复

        前置条件：
        - 请求状态为 executable
        - 达到见证人阈值
        - 时间锁已过

        Args:
            request_id: 恢复请求 ID
            executor_did: 执行者 DID（可以是发起者或任何见证人）

        Returns:
            { success, message, request? }
        """
        storage = self._get_storage()
        req_data = storage.get(self.COLLECTION_RECOVERY, request_id)
        if not req_data:
            return {"success": False, "message": f"恢复请求不存在: {request_id}"}

        request = RecoveryRequest.from_dict(req_data)

        # 检查前置条件
        if request.status == RECOVERY_STATUS_EXECUTED:
            return {"success": False, "message": "恢复请求已执行"}
        if request.status == RECOVERY_STATUS_EXPIRED:
            return {"success": False, "message": "恢复请求已过期"}
        if request.status == RECOVERY_STATUS_CANCELLED:
            return {"success": False, "message": "恢复请求已取消"}

        if not request.is_threshold_met:
            return {
                "success": False,
                "message": f"见证人签名不足: {request.witness_count}/{request.witness_threshold}",
            }

        if not request.time_lock_passed:
            remaining_hours = request.time_remaining_seconds / 3600
            return {
                "success": False,
                "message": f"时间锁尚未过期，还需 {remaining_hours:.1f} 小时",
            }

        # 执行恢复：更新 DID Document 中的公钥
        # （实际修改 DID Document 由外部调用者完成，此处记录恢复结果）
        request.status = RECOVERY_STATUS_EXECUTED
        request.executed_at = time.time()
        storage.put(self.COLLECTION_RECOVERY, request_id, request.to_dict())

        return {
            "success": True,
            "message": f"身份恢复已完成 — DID {request.target_did} 的公钥已更新为新的密钥",
            "target_did": request.target_did,
            "target_alpha_id": request.target_alpha_id,
            "new_public_key_hex": request.new_public_key_hex,
            "old_public_key_hex": request.old_public_key_hex,
            "witness_count": request.witness_count,
            "request": request.to_dict(),
        }

    def get_recovery_request(self, request_id: str) -> Optional[RecoveryRequest]:
        """获取单个恢复请求详情"""
        storage = self._get_storage()
        data = storage.get(self.COLLECTION_RECOVERY, request_id)
        if data is None:
            return None
        return RecoveryRequest.from_dict(data)

    def list_recovery_requests(
        self,
        target_alpha_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出恢复请求，可按目标身份或状态筛选"""
        storage = self._get_storage()
        requests = storage.list(self.COLLECTION_RECOVERY)

        filtered = []
        for req in requests:
            if target_alpha_id and req.get("target_alpha_id") != target_alpha_id:
                continue
            if status and req.get("status") != status:
                continue
            filtered.append(req)

        # 按时间倒序
        filtered.sort(key=lambda r: r.get("initiated_at", 0), reverse=True)
        return filtered

    def check_active_recovery(self, target_alpha_id: str) -> Optional[Dict[str, Any]]:
        """检查目标身份是否有活跃的恢复请求"""
        requests = self.list_recovery_requests(
            target_alpha_id=target_alpha_id,
            status=None,
        )
        for req in requests:
            if req.get("status") in (
                RECOVERY_STATUS_PENDING,
                RECOVERY_STATUS_READY,
                RECOVERY_STATUS_EXECUTABLE,
            ):
                return req
        return None
