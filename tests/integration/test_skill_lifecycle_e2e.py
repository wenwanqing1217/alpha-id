"""End-to-end Skill lifecycle integration tests"""

import json
import time
from pathlib import Path

from alpha_id.signer import AIDSigner
from alpha_id.skill_signer import (
    SkillPackage,
    SkillRegistry,
    SkillRuntime,
    SkillAttributionTracker,
    AttributionRecord,
    sign_skill,
    verify_skill,
    SkillSigningError,
)
from alpha_id.poe import PoEStore, PoEClient
from core.reputation import SkillReputation
import pytest


class TestSkillLifecycleE2E:
    def test_full_lifecycle(self, tmp_path):
        author = AIDSigner()
        author.generate()
        assert author.has_identity
        assert author.did.startswith("did:aid:")

        skill_file = tmp_path / "greeter.py"
        skill_file.write_text(
            'def main(params):\n    name = params.get("name", "World")\n    return f"Hello, {name}!"\n'
        )
        skill_content = skill_file.read_bytes()

        pkg = sign_skill(skill_file, author, name="greeter", version="1.0.0", description="A greeting skill")
        assert pkg.is_signed
        assert pkg.name == "greeter"
        assert pkg.version == "1.0.0"
        assert pkg.author_did == author.did
        assert len(pkg.signature) > 0

        registry = SkillRegistry(storage_dir=str(tmp_path / "registry"))
        reg_result = registry.register(pkg, content=skill_content)
        assert reg_result["success"]

        registered_pkg = registry.get("greeter")
        assert registered_pkg is not None
        stored_content = registry.get_content("greeter")
        assert stored_content == skill_content

        executor = AIDSigner()
        executor.generate()

        tracker = SkillAttributionTracker(storage_dir=str(tmp_path / "attrib"))
        poe_store = PoEStore(storage_dir=str(tmp_path / "poes"))
        poe_client = PoEClient(executor, store=poe_store)

        runtime = SkillRuntime(registry, tracker=tracker, poe_client=poe_client)
        result = runtime.execute("greeter", '{"name": "Alice"}', executor_did=executor.did)
        assert "Hello, Alice" in result

        author_stats = tracker.get_author_stats(author.did)
        assert author_stats["total_executions"] == 1
        assert author_stats["success_rate"] == 1.0
        assert author_stats["unique_executors"] == 1
        assert author_stats["avg_duration_ms"] >= 0

        score = SkillReputation.compute(author_stats)
        assert score > 0
        assert SkillReputation.compute_level(score) in ("S", "A", "B", "C", "D")

        assert poe_store.count() == 1
        poes = poe_store.list_for_skill("greeter")
        assert len(poes) == 1
        poe = poes[0]
        assert poe.skill_name == "greeter"
        assert poe.executor_did == executor.did
        assert poe.author_did == author.did
        assert poe.success is True
        assert poe.verify(executor.public_key)
        assert len(poe.poe_id) == 16

        for i in range(4):
            runtime.execute("greeter", '{"name": "User%d"}' % i, executor_did=executor.did)
        author_stats2 = tracker.get_author_stats(author.did)
        assert author_stats2["total_executions"] == 5
        assert author_stats2["unique_executors"] == 1

        executor2 = AIDSigner()
        executor2.generate()
        runtime.execute("greeter", '{"name": "Bob"}', executor_did=executor2.did)

        author_stats3 = tracker.get_author_stats(author.did)
        assert author_stats3["total_executions"] == 6
        assert author_stats3["unique_executors"] == 2
        assert author_stats3["success_rate"] == 1.0

        score_after = SkillReputation.compute(author_stats3)
        assert score_after >= score

        revoke_result = registry.revoke("greeter", reason="test revocation", signer=author)
        assert revoke_result["success"]
        assert registry.is_revoked("greeter")

        result_after_revoke = runtime.execute("greeter", "{}", executor_did=executor.did)
        assert "已被吊销" in result_after_revoke or "revoke" in result_after_revoke.lower()

        verify_result = verify_skill(skill_file, pkg, registry=registry)
        assert verify_result["valid"] is False
        assert verify_result["revoked"] is True

        entries = registry.list(include_revoked=False)
        assert all(not e["is_revoked"] for e in entries)
        assert "greeter" not in [e["name"] for e in entries]

        entries_all = registry.list(include_revoked=True)
        assert any(e["name"] == "greeter" and e["is_revoked"] for e in entries_all)

    def test_malicious_tamper_detected(self, tmp_path):
        author = AIDSigner()
        author.generate()

        skill_file = tmp_path / "safe.py"
        skill_file.write_text("def main(p): return 'safe'")
        content_original = skill_file.read_bytes()

        pkg = sign_skill(skill_file, author, name="safe-skill")
        registry = SkillRegistry(storage_dir=str(tmp_path / "reg"))
        registry.register(pkg, content=content_original)

        content_path = registry.get_content_path("safe-skill")
        assert content_path is not None
        content_path.write_bytes(b"MALICIOUS_CODE")
        runtime = SkillRuntime(registry)

        result = runtime.execute("safe-skill", "{}", executor_did="did:aid:attacker")
        # get_content returns None when hash mismatches, so execute sees "content unavailable"
        assert "不可用" in result or "hash" in result.lower()

        # verify_skill checks the original file (unchanged), so content_match is still True
        # but get_content should return None due to hash mismatch
        assert registry.get_content("safe-skill") is None

    def test_multiple_skills_independent(self, tmp_path):
        author = AIDSigner()
        author.generate()
        executor = AIDSigner()
        executor.generate()

        registry = SkillRegistry(storage_dir=str(tmp_path / "reg"))
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path / "attrib"))
        runtime = SkillRuntime(registry, tracker=tracker)

        skills = ["skill-a", "skill-b"]
        for name in skills:
            sf = tmp_path / f"{name}.py"
            sf.write_text("def main(p): return '" + name + " executed'")
            pkg = sign_skill(sf, author, name=name)
            registry.register(pkg, content=sf.read_bytes())

        for _ in range(3):
            runtime.execute("skill-a", "{}", executor_did=executor.did)
        runtime.execute("skill-b", "{}", executor_did=executor.did)

        stats = tracker.get_author_stats(author.did)
        assert stats["total_executions"] == 4

    def test_attribution_persistence(self, tmp_path):
        author = AIDSigner()
        author.generate()
        executor = AIDSigner()
        executor.generate()

        skill_file = tmp_path / "persist.py"
        skill_file.write_text("def main(p): return 'persist'")

        registry = SkillRegistry(storage_dir=str(tmp_path / "reg"))
        pkg = sign_skill(skill_file, author, name="persist-skill")
        registry.register(pkg, content=skill_file.read_bytes())

        attrib_dir = str(tmp_path / "attrib")
        tracker = SkillAttributionTracker(storage_dir=attrib_dir)
        runtime = SkillRuntime(registry, tracker=tracker)
        runtime.execute("persist-skill", "{}", executor_did=executor.did)

        tracker2 = SkillAttributionTracker(storage_dir=attrib_dir)
        stats = tracker2.get_author_stats(author.did)
        assert stats["total_executions"] == 1

    def test_skill_without_identity_rejected(self, tmp_path):
        skill_file = tmp_path / "anon.py"
        skill_file.write_text("def main(p): return 'anon'")
        signer = AIDSigner()
        with pytest.raises(SkillSigningError):
            sign_skill(skill_file, signer, name="anon")
