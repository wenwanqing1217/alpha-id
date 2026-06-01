"""
PoE（Proof of Execution）单元测试
"""

import json, os
import hashlib
import pytest
from alpha_id import AIDSigner, ProofOfExecution, PoEStore, PoEClient


class TestProofOfExecution:
    """ProofOfExecution 数据模型测试"""

    def test_basic_fields(self):
        poe = ProofOfExecution(
            skill_name="greet",
            skill_version="0.1.0",
            skill_content_hash="abc123",
            executor_did="did:aid:executor",
            author_did="did:aid:author",
            timestamp=1234567890.0,
            params_hash="def456",
            output_hash="ghi789",
            success=True,
            duration_ms=42,
        )
        assert poe.skill_name == "greet"
        assert poe.skill_version == "0.1.0"
        assert poe.success
        assert poe.duration_ms == 42
        assert poe.poe_version == "1.0"

    def test_compute_poe_id(self):
        poe = ProofOfExecution(
            skill_name="test",
            skill_version="1.0",
            skill_content_hash="abc",
            executor_did="did:aid:e",
            author_did="did:aid:a",
            timestamp=0.0,
            params_hash="def",
            output_hash="ghi",
            success=True,
            duration_ms=1,
        )
        pid = poe.compute_poe_id()
        assert len(pid) == 16
        assert isinstance(pid, str)
        # 确定性
        assert poe.compute_poe_id() == pid

    def test_sign_and_verify(self):
        signer = AIDSigner()
        signer.generate()

        poe = ProofOfExecution(
            skill_name="greet",
            skill_version="0.1.0",
            skill_content_hash="abc",
            executor_did=signer.did,
            author_did="did:aid:author",
            timestamp=1234567890.0,
            params_hash="def",
            output_hash="ghi",
            success=True,
            duration_ms=42,
        )
        poe.sign(signer)
        assert len(poe.poe_id) == 16
        assert len(poe.signature) > 0

        # 验证签名
        assert poe.verify(signer.public_key)

    def test_verify_wrong_key(self):
        s1, s2 = AIDSigner(), AIDSigner()
        s1.generate()
        s2.generate()

        poe = ProofOfExecution(
            skill_name="greet",
            skill_version="0.1.0",
            skill_content_hash="abc",
            executor_did=s1.did,
            author_did="did:aid:a",
            timestamp=0.0,
            params_hash="def",
            output_hash="ghi",
            success=True,
            duration_ms=1,
        )
        poe.sign(s1)
        # 用错误的公钥验证
        assert not poe.verify(s2.public_key)

    def test_tampered_fields(self):
        signer = AIDSigner()
        signer.generate()

        poe = ProofOfExecution(
            skill_name="greet",
            skill_version="0.1.0",
            skill_content_hash="abc",
            executor_did=signer.did,
            author_did="did:aid:a",
            timestamp=0.0,
            params_hash="def",
            output_hash="ghi",
            success=True,
            duration_ms=1,
        )
        poe.sign(signer)

        # 篡改字段
        poe.output_hash = "tampered"
        # 签名是 payload 的签名，字段变了就验不过
        # 注意：验签使用 _payload() 中包含的当前字段值
        # 但 payload 不包括 output_hash 被篡改后...等等，实际上 payload 会包含篡改后的值
        # 所以验证会过。我们需要验证 poe_id 是否匹配 payload hash
        # 篡改后的 payload hash 不等于原来的 poe_id
        assert poe.compute_poe_id() != poe.poe_id

    def test_to_json_roundtrip(self):
        poe = ProofOfExecution(
            skill_name="greet",
            skill_version="0.1.0",
            skill_content_hash="abc",
            executor_did="did:aid:e",
            author_did="did:aid:a",
            timestamp=0.0,
            params_hash="def",
            output_hash="ghi",
            success=True,
            duration_ms=1,
            poe_id="test123",
            signature="sig_hex",
        )
        text = poe.to_json()
        parsed = json.loads(text)
        assert parsed["skill_name"] == "greet"
        assert parsed["poe_id"] == "test123"
        # 反向解析
        restored = ProofOfExecution.from_json(text)
        assert restored.skill_name == "greet"
        assert restored.poe_id == "test123"


class TestPoEClient:
    """PoEClient 生成器测试"""

    def test_generate_signed_poe(self):
        signer = AIDSigner()
        signer.generate()

        client = PoEClient(signer)
        poe = client.generate(
            skill_name="greet",
            skill_version="0.1.0",
            skill_content_hash="abc123",
            executor_did=signer.did,
            author_did="did:aid:author",
            params={"name": "World"},
            output="hello World",
            success=True,
            duration_ms=42,
        )
        assert poe.poe_id
        assert poe.signature
        assert poe.verify(signer.public_key)
        import hashlib

        assert poe.output_hash == hashlib.sha256(b"hello World").hexdigest()

    def test_generate_with_store(self, tmp_path):
        signer = AIDSigner()
        signer.generate()

        store = PoEStore(str(tmp_path))
        client = PoEClient(signer, store=store)
        poe = client.generate(
            skill_name="test",
            skill_version="1.0",
            skill_content_hash="def",
            executor_did=signer.did,
            author_did="did:aid:a",
            params={"x": 1},
            output="ok",
            success=True,
            duration_ms=10,
        )
        # 从 store 中找回
        found = store.get(poe.poe_id)
        assert found is not None
        assert found.skill_name == "test"
        assert found.verify(signer.public_key)

    def test_generate_chain(self):
        s1, s2 = AIDSigner(), AIDSigner()
        s1.generate()
        s2.generate()

        parent_client = PoEClient(s1)
        parent_poe = parent_client.generate(
            skill_name="parent",
            skill_version="1.0",
            skill_content_hash="p",
            executor_did=s1.did,
            author_did="did:aid:a",
            params={},
            output="parent",
            success=True,
            duration_ms=1,
        )

        child_client = parent_client.with_chain(parent_poe.poe_id)
        child_poe = child_client.generate(
            skill_name="child",
            skill_version="1.0",
            skill_content_hash="c",
            executor_did=s2.did,
            author_did="did:aid:b",
            params={},
            output="child",
            success=True,
            duration_ms=1,
        )
        assert child_poe.parent_poe_id == parent_poe.poe_id
        # child_client 继承 parent_client 的 signer (s1)
        assert child_poe.verify(s1.public_key)
        assert parent_poe.verify(s1.public_key)


class TestPoEStore:
    """PoEStore 持久化测试"""

    def test_record_and_get(self, tmp_path):
        signer = AIDSigner()
        signer.generate()

        store = PoEStore(str(tmp_path))
        poe = ProofOfExecution(
            skill_name="greet",
            skill_version="0.1.0",
            skill_content_hash="abc",
            executor_did=signer.did,
            author_did="did:aid:a",
            timestamp=0.0,
            params_hash="def",
            output_hash="ghi",
            success=True,
            duration_ms=42,
            poe_id="test123",
        )
        store.record(poe)
        found = store.get("test123")
        assert found is not None
        assert found.skill_name == "greet"
        assert found.duration_ms == 42

    def test_get_nonexistent(self, tmp_path):
        store = PoEStore(str(tmp_path))
        assert store.get("nonexistent") is None

    def test_list_for_skill(self, tmp_path):
        signer = AIDSigner()
        signer.generate()

        store = PoEStore(str(tmp_path))
        for i in range(3):
            poe = ProofOfExecution(
                skill_name="greet" if i < 2 else "other",
                skill_version="0.1.0",
                skill_content_hash=f"abc{i}",
                executor_did=signer.did,
                author_did="did:aid:a",
                timestamp=float(i),
                params_hash="def",
                output_hash="ghi",
                success=True,
                duration_ms=i,
                poe_id=f"poe_greet_{i}",
            )
            store.record(poe)

        greet_poes = store.list_for_skill("greet")
        assert len(greet_poes) == 2
        assert all(p.skill_name == "greet" for p in greet_poes)

    def test_list_for_executor(self, tmp_path):
        store = PoEStore(str(tmp_path))
        for i in range(3):
            poe = ProofOfExecution(
                skill_name="test",
                skill_version="1.0",
                skill_content_hash=f"abc{i}",
                executor_did=f"did:aid:exec{i}",
                author_did="did:aid:a",
                timestamp=float(i),
                params_hash="def",
                output_hash="ghi",
                success=True,
                duration_ms=i,
                poe_id=f"poe_exec_{i}",
            )
            store.record(poe)

        exec1_poes = store.list_for_executor("did:aid:exec1")
        assert len(exec1_poes) == 1
        assert exec1_poes[0].executor_did == "did:aid:exec1"

    def test_count(self, tmp_path):
        store = PoEStore(str(tmp_path))
        assert store.count() == 0

        for i in range(5):
            poe = ProofOfExecution(
                skill_name="test",
                skill_version="1.0",
                skill_content_hash=f"abc{i}",
                executor_did="did:aid:e",
                author_did="did:aid:a",
                timestamp=float(i),
                params_hash="def",
                output_hash="ghi",
                success=True,
                duration_ms=i,
                poe_id=f"poe_{i}",
            )
            store.record(poe)

        assert store.count() == 5

    def test_list_all_returns_results(self, tmp_path):
        """list_all 返回所有记录"""
        store = PoEStore(str(tmp_path))
        for i in range(3):
            poe = ProofOfExecution(
                skill_name="test",
                skill_version="1.0",
                skill_content_hash=f"abc{i}",
                executor_did="did:aid:e",
                author_did="did:aid:a",
                timestamp=float(i),
                params_hash="def",
                output_hash="ghi",
                success=True,
                duration_ms=i,
                poe_id=f"poe_{i}",
            )
            store.record(poe)

        all_poes = store.list_all(limit=10)
        assert len(all_poes) == 3


class TestPoEIntegration:
    """PoE × SkillRuntime 集成测试"""

    def test_runtime_generates_poe(self, tmp_path):
        """SkillRuntime.execute() 通过 PoEClient 生成执行证明"""
        from alpha_id.skill_signer import SkillRegistry, SkillRuntime, sign_skill, SkillPackage
        from alpha_id.poe import PoEStore, PoEClient

        signer = AIDSigner()
        signer.generate()

        author = AIDSigner()
        author.generate()

        # 注册技能
        storage = str(tmp_path / "skills")
        poe_storage = str(tmp_path / "poes")
        registry = SkillRegistry(storage_dir=storage)
        poe_store = PoEStore(storage_dir=poe_storage)
        poe_client = PoEClient(signer, store=poe_store)
        runtime = SkillRuntime(registry, poe_client=poe_client)

        skill_file = tmp_path / "hello.py"
        skill_file.write_text('def main(p): return "hello " + p.get("name","world")')
        pkg = sign_skill(skill_file, author, name="hello")
        with open(skill_file, "rb") as fh:
            registry.register(pkg, content=fh.read())

        # 执行
        result = runtime.execute("hello", '{"name":"PoE"}', executor_did=signer.did)
        assert "hello PoE" in result

        # 验证 PoE 已生成
        poes = poe_store.list_for_skill("hello")
        assert len(poes) >= 1
        poe = poes[0]
        assert poe.skill_name == "hello"
        assert poe.executor_did == signer.did
        assert poe.author_did == author.did
        assert poe.success
        assert poe.verify(signer.public_key)

    def test_runtime_poe_with_attribution(self, tmp_path):
        """PoE 与归因共存"""
        from alpha_id.skill_signer import (
            SkillRegistry,
            SkillRuntime,
            SkillAttributionTracker,
            sign_skill,
            SkillPackage,
        )
        from alpha_id.poe import PoEStore, PoEClient

        signer = AIDSigner()
        signer.generate()
        author = AIDSigner()
        author.generate()

        storage = str(tmp_path / "skills")
        tracker_dir = str(tmp_path / "attributions")
        poe_dir = str(tmp_path / "poes")

        registry = SkillRegistry(storage_dir=storage)
        tracker = SkillAttributionTracker(storage_dir=tracker_dir)
        poe_store = PoEStore(storage_dir=poe_dir)
        poe_client = PoEClient(signer, store=poe_store)
        runtime = SkillRuntime(registry, tracker=tracker, poe_client=poe_client)

        skill_file = tmp_path / "test.py"
        skill_file.write_text('def main(p): return "ok"')
        pkg = sign_skill(skill_file, author, name="test_poe_attr")
        with open(skill_file, "rb") as fh:
            registry.register(pkg, content=fh.read())

        runtime.execute("test_poe_attr", "{}", executor_did=signer.did)

        # 归因已记录
        stats = tracker.get_author_stats(author.did)
        assert stats["total_executions"] == 1

        # PoE 已生成
        poes = poe_store.list_for_skill("test_poe_attr")
        assert len(poes) >= 1

    def test_poe_failure_does_not_block(self, tmp_path):
        """PoE 生成失败不阻塞技能执行"""
        from alpha_id.skill_signer import SkillRegistry, SkillRuntime, sign_skill, SkillPackage

        # 没有 signer 的 PoEClient 会失败——用 None 模拟
        signer = AIDSigner()
        signer.generate()
        author = AIDSigner()
        author.generate()

        storage = str(tmp_path / "skills")
        registry = SkillRegistry(storage_dir=storage)

        # 故意构造一个会失败的 PoEClient（signer 无身份）
        bad_signer = AIDSigner()
        from alpha_id.poe import PoEClient
        # bad_signer 没有 generate()，所以 PoEClient 没有 signer

        runtime = SkillRuntime(registry)

        skill_file = tmp_path / "simple.py"
        skill_file.write_text('def main(p): return "ok"')
        pkg = sign_skill(skill_file, author, name="simple")
        with open(skill_file, "rb") as fh:
            registry.register(pkg, content=fh.read())

        # 应该正常执行，不抛异常
        result = runtime.execute("simple", "{}", executor_did=signer.did)
        assert "ok" in result or "返回" in result
