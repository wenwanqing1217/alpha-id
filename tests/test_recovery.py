"""
RecoveryEngine 身份恢复单元测试
"""

import time
import json

from core.recovery import (
    RecoveryEngine,
    RecoveryRequest,
    WitnessRecord,
    RECOVERY_STATUS_PENDING,
    RECOVERY_STATUS_READY,
    RECOVERY_STATUS_EXECUTABLE,
    RECOVERY_STATUS_EXECUTED,
    RECOVERY_STATUS_EXPIRED,
    RECOVERY_STATUS_CANCELLED,
)
from core.storage import JsonStorage


# ── 测试用数据 ──

TARGET_DID = "did:aid:Alpha-Rec-Test"
TARGET_AID = "Alpha-Rec-Test"
INITIATOR_DID = "did:aid:Alpha-Rec-Initiator"
NEW_PUB_KEY = "a1b2c3d4e5f6" * 5  # 32 bytes worth of hex
OLD_PUB_KEY = "f6e5d4c3b2a1" * 5
WITNESSES = [
    "did:aid:Witness-001",
    "did:aid:Witness-002",
    "did:aid:Witness-003",
]


def test_recovery_request_model():
    """RecoveryRequest 数据模型构造与转换"""
    req = RecoveryRequest(
        request_id="rec_test_001",
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        initiated_at=time.time(),
        time_lock_hours=24,
        witness_threshold=2,
        witnesses=WITNESSES,
        message="Test recovery",
    )
    assert req.status == RECOVERY_STATUS_PENDING
    assert req.witness_count == 0
    assert not req.is_threshold_met
    assert not req.time_lock_passed

    # to_dict / from_dict 往返
    d = req.to_dict()
    req2 = RecoveryRequest.from_dict(d)
    assert req2.request_id == "rec_test_001"
    assert req2.target_did == TARGET_DID
    assert req2.witness_threshold == 2


def test_witness_record_model():
    """WitnessRecord 数据模型"""
    rec = WitnessRecord(
        alpha_id="Witness-001",
        did="did:aid:Witness-001",
        added_at=time.time(),
        added_by=TARGET_AID,
        label="家人",
    )
    d = rec.to_dict()
    rec2 = WitnessRecord.from_dict(d)
    assert rec2.alpha_id == "Witness-001"
    assert rec2.label == "家人"


def test_initiate_recovery(tmp_path):
    """发起恢复请求"""
    db_file = str(tmp_path / "rec_init.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    result = engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
        time_lock_hours=24,
        witness_threshold=2,
        message="我需要恢复身份",
    )

    assert result["success"]
    assert "request_id" in result
    assert result["request"]["status"] == RECOVERY_STATUS_PENDING

    # 验证存储
    req = engine.get_recovery_request(result["request_id"])
    assert req is not None
    assert req.target_alpha_id == TARGET_AID
    assert req.witnesses == WITNESSES


def test_initiate_cancels_old(tmp_path):
    """新发起自动作废旧的待处理请求"""
    db_file = str(tmp_path / "rec_cancel.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    # 第一次发起
    r1 = engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
    )
    rid1 = r1["request_id"]

    # 第二次发起
    r2 = engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
    )

    # 第一次的应被取消
    req1 = engine.get_recovery_request(rid1)
    assert req1.status == RECOVERY_STATUS_CANCELLED


def test_sign_recovery(tmp_path):
    """见证人签名"""
    db_file = str(tmp_path / "rec_sign.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    result = engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
        witness_threshold=2,
    )
    rid = result["request_id"]

    # 第一个见证人签名
    r1 = engine.sign_recovery(rid, "did:aid:Witness-001", "sig_001_hex")
    assert r1["success"]
    assert r1["witness_count"] == 1
    assert not r1["threshold_met"]
    assert r1["new_status"] == RECOVERY_STATUS_PENDING

    # 重复签名应失败
    r1_dup = engine.sign_recovery(rid, "did:aid:Witness-001", "sig_001_hex")
    assert not r1_dup["success"]

    # 第二个见证人签名 → 达到阈值
    r2 = engine.sign_recovery(rid, "did:aid:Witness-002", "sig_002_hex")
    assert r2["success"]
    assert r2["witness_count"] == 2
    assert r2["threshold_met"]
    assert r2["new_status"] == RECOVERY_STATUS_READY


def test_sign_not_in_witness_list(tmp_path):
    """不在见证人列表中的人不能签名"""
    db_file = str(tmp_path / "rec_sign_invalid.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    result = engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
    )
    rid = result["request_id"]

    # 不在列表的见证人签名
    r = engine.sign_recovery(rid, "did:aid:Stranger", "sig_stranger")
    assert not r["success"]
    assert "不在该请求的见证人列表中" in r["message"]


def test_check_readiness(tmp_path):
    """检查恢复就绪状态"""
    db_file = str(tmp_path / "rec_readiness.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    result = engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
        time_lock_hours=24,
        witness_threshold=1,  # 只需要 1 个签名，方便测试
    )
    rid = result["request_id"]

    # 未签名：不可执行
    status = engine.check_readiness(rid)
    assert not status["threshold_met"]
    assert not status["is_ready"]

    # 签名后：达到阈值但时间锁未过
    engine.sign_recovery(rid, "did:aid:Witness-001", "sig_001")
    status = engine.check_readiness(rid)
    assert status["threshold_met"]
    assert not status["time_lock_passed"]
    assert status["status"] == RECOVERY_STATUS_READY


def test_execute_recovery_not_ready(tmp_path):
    """尝试执行未就绪的恢复请求应失败"""
    db_file = str(tmp_path / "rec_exec_not_ready.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    result = engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
        time_lock_hours=24,
        witness_threshold=1,
    )
    rid = result["request_id"]

    # 未签名就执行
    r = engine.execute_recovery(rid)
    assert not r["success"]

    # 签名但时间锁没过
    engine.sign_recovery(rid, "did:aid:Witness-001", "sig_001")
    r = engine.execute_recovery(rid)
    assert not r["success"]
    assert "时间锁" in r["message"]


def test_execute_recovery_success(tmp_path):
    """成功执行恢复（阈值满足 + 时间锁过期）"""
    db_file = str(tmp_path / "rec_exec_ok.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    # 使用 1 小时时间锁
    result = engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
        time_lock_hours=0.00001,  # 极短时间锁（36ms）
        witness_threshold=1,
    )
    rid = result["request_id"]

    engine.sign_recovery(rid, "did:aid:Witness-001", "sig_001")
    time.sleep(0.05)  # 等时间锁过

    r = engine.execute_recovery(rid)
    assert r["success"]
    assert r["target_did"] == TARGET_DID
    assert r["new_public_key_hex"] == NEW_PUB_KEY

    # 不应重复执行
    r2 = engine.execute_recovery(rid)
    assert not r2["success"]


def test_execute_recovery_twice_fails(tmp_path):
    """重复执行已完成的恢复请求应失败"""
    db_file = str(tmp_path / "rec_exec_twice.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    result = engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
        time_lock_hours=0.00001,
        witness_threshold=1,
    )
    rid = result["request_id"]
    engine.sign_recovery(rid, "did:aid:Witness-001", "sig_001")
    time.sleep(0.01)

    engine.execute_recovery(rid)
    r = engine.execute_recovery(rid)
    assert not r["success"]


def test_witness_management(tmp_path):
    """见证人增删查"""
    db_file = str(tmp_path / "rec_witness.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    # 添加
    r1 = engine.add_witness(TARGET_AID, "Witness-001", "did:aid:Witness-001", "家人")
    assert r1["success"]

    r2 = engine.add_witness(TARGET_AID, "Witness-002", "did:aid:Witness-002", "同事")
    assert r2["success"]

    # 重复添加失败
    r3 = engine.add_witness(TARGET_AID, "Witness-001", "did:aid:Witness-001")
    assert not r3["success"]

    # 列出
    witnesses = engine.list_witnesses(TARGET_AID)
    assert len(witnesses) == 2

    # 移除
    r4 = engine.remove_witness(TARGET_AID, "Witness-001")
    assert r4["success"]
    witnesses = engine.list_witnesses(TARGET_AID)
    assert len(witnesses) == 1

    # 移除不存在的
    r5 = engine.remove_witness(TARGET_AID, "Nobody")
    assert not r5["success"]


def test_list_recovery_requests(tmp_path):
    """列出恢复请求"""
    db_file = str(tmp_path / "rec_list.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    # 发起两个
    engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
    )
    engine.initiate_recovery(
        target_did="did:aid:Other",
        target_alpha_id="Other",
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
    )

    # 按目标筛选
    results = engine.list_recovery_requests(target_alpha_id=TARGET_AID)
    assert len(results) == 1
    assert results[0]["target_alpha_id"] == TARGET_AID

    # 全部
    all_reqs = engine.list_recovery_requests()
    assert len(all_reqs) >= 2


def test_check_active_recovery(tmp_path):
    """检查是否有活跃恢复请求"""
    db_file = str(tmp_path / "rec_active.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    # 无活跃
    assert engine.check_active_recovery(TARGET_AID) is None

    # 发起后
    engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
    )
    active = engine.check_active_recovery(TARGET_AID)
    assert active is not None
    assert active["status"] == RECOVERY_STATUS_PENDING


def test_recovery_expiry(tmp_path):
    """恢复请求过期"""
    db_file = str(tmp_path / "rec_expiry.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    # 设置极短的过期时间
    engine.REQUEST_EXPIRY_DAYS = 0  # 0 天过期

    result = engine.initiate_recovery(
        target_did=TARGET_DID,
        target_alpha_id=TARGET_AID,
        new_public_key_hex=NEW_PUB_KEY,
        old_public_key_hex=OLD_PUB_KEY,
        initiator=INITIATOR_DID,
        witnesses=WITNESSES,
        time_lock_hours=0.00001,
        witness_threshold=1,
    )
    rid = result["request_id"]
    engine.sign_recovery(rid, "did:aid:Witness-001", "sig_001")

    # 检查应标记为过期
    status = engine.check_readiness(rid)
    assert status["status"] == RECOVERY_STATUS_EXPIRED
