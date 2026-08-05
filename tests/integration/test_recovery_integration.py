"""
RecoveryEngine × TwinBrain 集成测试

验证恢复引擎与现有系统的兼容性。
"""

import time

from core.recovery import RECOVERY_STATUS_EXECUTED, RecoveryEngine
from core.storage import JsonStorage


def test_recovery_uses_json_storage(tmp_path):
    """恢复引擎可以通过 JsonStorage 工作"""
    db_file = str(tmp_path / "integ_rec.json")
    storage = JsonStorage(db_file)

    engine = RecoveryEngine(storage=storage)
    result = engine.initiate_recovery(
        target_did="did:aid:Alpha-Int-Rec",
        target_alpha_id="Alpha-Int-Rec",
        new_public_key_hex="aa" * 32,
        old_public_key_hex="bb" * 32,
        initiator="did:aid:Alpha-Int-Rec",
        witnesses=["did:aid:Witness-A", "did:aid:Witness-B"],
        time_lock_hours=0.00001,
        witness_threshold=1,
    )
    assert result["success"]
    assert engine.get_recovery_request(result["request_id"]) is not None


def test_recovery_prevents_duplicate_active(tmp_path):
    """同身份只能有一个活跃恢复请求"""
    db_file = str(tmp_path / "integ_dup.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    r1 = engine.initiate_recovery(
        target_did="did:aid:Dupe",
        target_alpha_id="Dupe",
        new_public_key_hex="aa" * 32,
        old_public_key_hex="bb" * 32,
        initiator="did:aid:Dupe",
        witnesses=["did:aid:W1"],
    )
    r2 = engine.initiate_recovery(
        target_did="did:aid:Dupe",
        target_alpha_id="Dupe",
        new_public_key_hex="cc" * 32,
        old_public_key_hex="bb" * 32,
        initiator="did:aid:Dupe",
        witnesses=["did:aid:W1"],
    )

    # r1 应被取消
    req1 = engine.get_recovery_request(r1["request_id"])
    assert req1.status == "cancelled"

    # 活跃的只有 r2
    active = engine.check_active_recovery("Dupe")
    assert active["request_id"] == r2["request_id"]


def test_full_recovery_flow(tmp_path):
    """完整的社交恢复流程"""
    db_file = str(tmp_path / "integ_flow.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    # 1. 设置见证人
    engine.add_witness("Alpha-Owner", "Witness-A", "did:aid:Witness-A", "家人")
    engine.add_witness("Alpha-Owner", "Witness-B", "did:aid:Witness-B", "同事")
    engine.add_witness("Alpha-Owner", "Witness-C", "did:aid:Witness-C", "朋友")

    witnesses = engine.list_witnesses("Alpha-Owner")
    assert len(witnesses) == 3

    # 2. 发起恢复
    result = engine.initiate_recovery(
        target_did="did:aid:Alpha-Owner",
        target_alpha_id="Alpha-Owner",
        new_public_key_hex="new_pub_key_hex_1234",
        old_public_key_hex="old_pub_key_hex_5678",
        initiator="did:aid:Alpha-Owner",
        witnesses=["did:aid:Witness-A", "did:aid:Witness-B", "did:aid:Witness-C"],
        time_lock_hours=0.00001,
        witness_threshold=2,
        message="我丢了我的密钥，帮我恢复！",
    )
    rid = result["request_id"]
    assert result["success"]

    # 3. 检查状态
    status = engine.check_readiness(rid)
    assert status["status"] == "pending"

    # 4. Witness-A 签名
    r = engine.sign_recovery(rid, "did:aid:Witness-A", "sig_a")
    assert r["success"]
    assert r["witness_count"] == 1

    # 5. Witness-B 签名 → 达到阈值
    r = engine.sign_recovery(rid, "did:aid:Witness-B", "sig_b")
    assert r["success"]
    assert r["witness_count"] == 2
    assert r["threshold_met"]

    # 6. 时间锁过后执行
    time.sleep(0.05)
    execute_result = engine.execute_recovery(rid)
    assert execute_result["success"]
    assert execute_result["new_public_key_hex"] == "new_pub_key_hex_1234"

    # 7. 验证最终状态
    req = engine.get_recovery_request(rid)
    assert req.status == RECOVERY_STATUS_EXECUTED
    assert req.executed_at is not None


def test_witness_cannot_sign_after_execution(tmp_path):
    """恢复执行后不能再签名"""
    db_file = str(tmp_path / "integ_no_sign_after.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    result = engine.initiate_recovery(
        target_did="did:aid:Alpha",
        target_alpha_id="Alpha",
        new_public_key_hex="aa" * 32,
        old_public_key_hex="bb" * 32,
        initiator="did:aid:Alpha",
        witnesses=["did:aid:W1"],
        time_lock_hours=0.00001,
        witness_threshold=1,
    )
    rid = result["request_id"]
    engine.sign_recovery(rid, "did:aid:W1", "sig1")
    time.sleep(0.01)
    engine.execute_recovery(rid)

    # 再签名应失败
    r = engine.sign_recovery(rid, "did:aid:W1", "sig2")
    assert not r["success"]


def test_multiple_identities_independent(tmp_path):
    """不同身份的恢复请求互相独立"""
    db_file = str(tmp_path / "integ_multi.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    # A 发起
    a = engine.initiate_recovery(
        target_did="did:aid:A",
        target_alpha_id="A",
        new_public_key_hex="aa" * 32,
        old_public_key_hex="bb" * 32,
        initiator="did:aid:A",
        witnesses=["did:aid:W1"],
    )
    # B 发起
    b = engine.initiate_recovery(
        target_did="did:aid:B",
        target_alpha_id="B",
        new_public_key_hex="cc" * 32,
        old_public_key_hex="dd" * 32,
        initiator="did:aid:B",
        witnesses=["did:aid:W2"],
    )

    # A 的请求不应影响 B
    assert engine.get_recovery_request(a["request_id"]).status == "pending"
    assert engine.get_recovery_request(b["request_id"]).status == "pending"


def test_recovery_auto_status_progression(tmp_path):
    """check_readiness 自动推进状态 pending → ready → executable"""
    db_file = str(tmp_path / "integ_auto_progress.json")
    storage = JsonStorage(db_file)
    engine = RecoveryEngine(storage=storage)

    # time_lock_hours=0.0001 ≈ 0.36s，留足余量避免 CI/负载下 flaky
    result = engine.initiate_recovery(
        target_did="did:aid:Auto",
        target_alpha_id="Auto",
        new_public_key_hex="aa" * 32,
        old_public_key_hex="bb" * 32,
        initiator="did:aid:Auto",
        witnesses=["did:aid:W1"],
        time_lock_hours=0.0001,
        witness_threshold=1,
    )
    rid = result["request_id"]

    # 签名 → 状态应为 ready
    engine.sign_recovery(rid, "did:aid:W1", "sig1")
    status = engine.check_readiness(rid)
    assert status["status"] == "ready"  # 刚签名，时间锁尚未过

    # 等时间锁过，check_readiness 会推进到 executable
    time.sleep(0.5)
    status = engine.check_readiness(rid)
    assert status["status"] == "executable"
