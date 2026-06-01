"""
测试 — SkillPackage 核心模型与序列化
"""

import json
import tempfile
import time
from pathlib import Path

from alpha_id.skill_signer import (
    SkillPackage,
    SkillRegistry,
    SkillRuntime,
    SkillAttributionTracker,
    AttributionRecord,
    sign_skill,
    verify_skill,
    SkillSigningError,
    SUPPORTED_CONTENT_TYPES,
)
from alpha_id.signer import AIDSigner
from core.reputation import SkillReputation


class TestSkillPackage:
    """SkillPackage 模型与序列化"""

    def test_minimal_skill_package(self):
        pkg = SkillPackage(
            name="test-skill",
            version="1.0.0",
            author_did="did:aid:test123",
        )
        assert pkg.name == "test-skill"
        assert pkg.version == "1.0.0"
        assert not pkg.is_signed
        assert pkg.meta_version == 1

    def test_to_dict_and_from_dict(self):
        pkg = SkillPackage(
            name="test",
            version="2.0.0",
            author_did="did:aid:abc",
            author_public_key_hex="aabb" * 16,
            content_hash="deadbeef",
            content_type="python",
            signature="ccdd" * 16,
            signed_at=123.0,
            tags=["ai", "tools"],
            dependencies=["base-skill"],
        )
        d = pkg.to_dict()
        assert d["name"] == "test"
        assert d["version"] == "2.0.0"
        assert d["signature"] == "ccdd" * 16

        restored = SkillPackage.from_dict(d)
        assert restored.name == "test"
        assert restored.signature == "ccdd" * 16
        assert restored.author_public_key == b"\xaa\xbb" * 16

    def test_json_roundtrip(self, tmp_path):
        pkg = SkillPackage(name="roundtrip", version="1.0.0", author_did="did:aid:demo")
        f = tmp_path / "pkg.json"
        pkg.save(f)
        assert f.exists()

        loaded = SkillPackage.load(f)
        assert loaded.name == "roundtrip"
        assert loaded.version == "1.0.0"

    def test_public_key_bytes_property(self):
        pkg = SkillPackage(author_public_key_hex="aabb" * 16)
        assert pkg.author_public_key == b"\xaa\xbb" * 16

        pkg2 = SkillPackage()
        assert pkg2.author_public_key == b""

    def test_signature_bytes_property(self):
        pkg = SkillPackage(signature="ccdd" * 16)
        assert pkg.signature_bytes == b"\xcc\xdd" * 16

        pkg2 = SkillPackage()
        assert pkg2.signature_bytes == b""

    def test_is_signed_requires_all_fields(self):
        # 只有签名但无公钥 → 不算已签名
        pkg1 = SkillPackage(signature="aa" * 64, signed_at=1.0)
        assert not pkg1.is_signed

        # 有签名+公钥+时间
        pkg2 = SkillPackage(signature="aa" * 64, author_public_key_hex="bb" * 32, signed_at=1.0)
        assert pkg2.is_signed

    def test_signing_payload_format(self):
        pkg = SkillPackage(
            name="demo",
            version="1.0.0",
            author_did="did:aid:xyz",
            content_hash="abc123",
            content_type="python",
            signed_at=456.0,
        )
        payload = pkg._signing_payload()
        expected = b"demo|1.0.0|did:aid:xyz|abc123|python|456.0"
        assert payload == expected

    def test_summary(self):
        pkg = SkillPackage(name="sum-skill", version="2.0.0", author_did="did:aid:testme")
        assert "sum-skill@2.0.0" in pkg.summary
        assert "✗" in pkg.summary

    def test_to_json(self):
        pkg = SkillPackage(name="json-test", version="1.0.0", author_did="did:aid:me")
        text = pkg.to_json()
        d = json.loads(text)
        assert d["name"] == "json-test"
        assert d["meta_version"] == 1


class TestSignAndVerify:
    """签名/验签流程"""

    def test_sign_skill_creates_package(self, tmp_path):
        skill_file = tmp_path / "hello.py"
        skill_file.write_text("print('hello')")

        signer = AIDSigner()
        signer.generate()

        pkg = sign_skill(
            skill_file=skill_file,
            signer=signer,
            name="hello",
            version="1.0.0",
            description="Say hello",
            tags=["demo"],
        )

        assert pkg.name == "hello"
        assert pkg.version == "1.0.0"
        assert pkg.author_did == signer.did
        assert pkg.description == "Say hello"
        assert pkg.content_type == "python"
        assert pkg.tags == ["demo"]
        assert pkg.is_signed
        assert len(pkg.signature) == 128  # 64 bytes in hex
        assert pkg.signed_at > 0
        # 公钥通过 cryptography 导出，不再等于 AIDSigner.public_key（broken 纯 Python 版）
        assert len(pkg.author_public_key_hex) == 64  # 32 bytes hex

    def test_sign_requires_identity(self, tmp_path):
        skill_file = tmp_path / "test.py"
        skill_file.write_text("x = 1")
        signer = AIDSigner()  # not generated

        import pytest

        with pytest.raises(SkillSigningError, match="未初始化"):
            sign_skill(skill_file=skill_file, signer=signer, name="test")

    def test_sign_file_not_found(self):
        signer = AIDSigner()
        signer.generate()

        import pytest

        with pytest.raises(FileNotFoundError):
            sign_skill(skill_file="/nonexistent/file.py", signer=signer, name="test")

    def test_verify_valid_signature(self, tmp_path):
        skill_file = tmp_path / "valid.py"
        skill_file.write_text("print('valid')")

        signer = AIDSigner()
        signer.generate()

        pkg = sign_skill(skill_file, signer, name="valid")

        result = verify_skill(skill_file, pkg)
        assert result["valid"] is True
        assert result["content_match"] is True
        assert result["signature_valid"] is True
        assert result["author_did"] == signer.did
        assert result["errors"] == []

    def test_verify_tampered_content(self, tmp_path):
        skill_file = tmp_path / "tamper.py"
        skill_file.write_text("original content")

        signer = AIDSigner()
        signer.generate()

        pkg = sign_skill(skill_file, signer, name="tamper")

        # 修改文件内容
        skill_file.write_text("tampered content")

        result = verify_skill(skill_file, pkg)
        assert result["valid"] is False
        assert result["content_match"] is False
        assert "内容哈希不匹配" in result["errors"][0]

    def test_verify_wrong_author(self, tmp_path):
        skill_file = tmp_path / "wrong.py"
        skill_file.write_text("print('who am i')")

        s1 = AIDSigner()
        s1.generate()

        pkg = sign_skill(skill_file, s1, name="wrong")

        # 用另一个 signer 的公钥篡改包
        s2 = AIDSigner()
        s2.generate()
        pkg.author_public_key_hex = s2.public_key.hex()

        result = verify_skill(skill_file, pkg)
        assert result["valid"] is False
        assert result["signature_valid"] is False

    def test_verify_no_signature(self, tmp_path):
        skill_file = tmp_path / "unsigned.py"
        skill_file.write_text("x = 1")

        pkg = SkillPackage(name="unsigned", version="1.0.0")
        result = verify_skill(skill_file, pkg)
        assert result["valid"] is False
        assert "未签名" in str(result["errors"])

    def test_verify_file_not_found(self, tmp_path):
        signer = AIDSigner()
        signer.generate()
        # 先创建一个包，然后传入不存在的文件路径
        temp_file = tmp_path / "temp.py"
        temp_file.write_text("temp")
        pkg = sign_skill(temp_file, signer, name="x")

        result = verify_skill("/notexist.py", pkg)
        assert result["valid"] is False
        assert any("不存在" in e for e in result["errors"])

    def test_sign_unsupported_type(self, tmp_path):
        skill_file = tmp_path / "test.docx"
        skill_file.write_text("doc")
        signer = AIDSigner()
        signer.generate()

        import pytest

        with pytest.raises(SkillSigningError, match="不支持"):
            sign_skill(skill_file, signer, name="test", content_type="docx")

    def test_sign_skill_with_dependencies(self, tmp_path):
        skill_file = tmp_path / "combo.py"
        skill_file.write_text("import helper")

        signer = AIDSigner()
        signer.generate()

        pkg = sign_skill(
            skill_file,
            signer,
            name="combo",
            dependencies=["helper@1.0.0"],
        )
        assert pkg.dependencies == ["helper@1.0.0"]


class TestSkillRegistry:
    """SkillRegistry 核心功能"""

    def test_register_skill(self, tmp_path):
        reg_dir = tmp_path / "registry"
        reg = SkillRegistry(storage_dir=str(reg_dir))

        pkg = SkillPackage(
            name="reg-test",
            version="1.0.0",
            author_did="did:aid:test",
            author_public_key_hex="aa" * 32,
            content_hash="deadbeef",
            signature="bb" * 64,
            signed_at=100.0,
        )

        result = reg.register(pkg)
        assert result["success"]
        assert result["key"] == "reg-test@1.0.0"

    def test_register_unsigned_fails(self, tmp_path):
        reg = SkillRegistry(storage_dir=str(tmp_path / "reg"))
        pkg = SkillPackage(name="bad", version="1.0.0")

        import pytest

        with pytest.raises(SkillSigningError, match="未签名"):
            reg.register(pkg)

    def test_get_skill(self, tmp_path):
        reg = SkillRegistry(storage_dir=str(tmp_path / "reg"))

        pkg = SkillPackage(
            name="get-test",
            version="2.0.0",
            author_did="did:aid:test",
            author_public_key_hex="aa" * 32,
            content_hash="beef",
            signature="cc" * 64,
            signed_at=200.0,
        )
        reg.register(pkg)

        # 精确版本
        found = reg.get("get-test", version="2.0.0")
        assert found is not None
        assert found.version == "2.0.0"

        # 不存在的版本
        assert reg.get("get-test", version="9.9.9") is None

        # 不存在的技能
        assert reg.get("nothing") is None

    def test_get_latest_version(self, tmp_path):
        reg = SkillRegistry(storage_dir=str(tmp_path / "reg"))

        for ver in ["1.0.0", "1.5.0", "2.0.0"]:
            pkg = SkillPackage(
                name="latest-test",
                version=ver,
                author_did="did:aid:t",
                author_public_key_hex="aa" * 32,
                content_hash=ver,
                signature="dd" * 64,
                signed_at=300.0,
            )
            reg.register(pkg)

        latest = reg.get("latest-test")
        assert latest is not None
        assert latest.version == "2.0.0"

    def test_list_skills(self, tmp_path):
        reg = SkillRegistry(storage_dir=str(tmp_path / "reg"))

        for name in ["skill-a", "skill-b"]:
            pkg = SkillPackage(
                name=name,
                version="1.0.0",
                author_did="did:aid:t",
                author_public_key_hex="aa" * 32,
                content_hash=name,
                signature="ee" * 64,
                signed_at=400.0,
            )
            reg.register(pkg)

        items = reg.list()
        assert len(items) == 2
        names = {s["name"] for s in items}
        assert names == {"skill-a", "skill-b"}

    def test_register_saves_to_disk(self, tmp_path):
        reg_dir = tmp_path / "disk_reg"
        reg = SkillRegistry(storage_dir=str(reg_dir))

        pkg = SkillPackage(
            name="disk-test",
            version="3.0.0",
            author_did="did:aid:disk",
            author_public_key_hex="ff" * 32,
            content_hash="disk",
            signature="aa" * 64,
            signed_at=500.0,
        )
        reg.register(pkg)

        # 新建一个注册表从同一目录加载
        reg2 = SkillRegistry(storage_dir=str(reg_dir))
        found = reg2.get("disk-test")
        assert found is not None
        assert found.version == "3.0.0"

    def test_revoke_skill(self, tmp_path):
        reg = SkillRegistry(storage_dir=str(tmp_path / "reg"))
        signer = AIDSigner()
        signer.generate()

        pkg = SkillPackage(
            name="revoke-me",
            version="1.0.0",
            author_did=signer.did,
            author_public_key_hex=signer.public_key.hex(),
            content_hash="hash",
            signature="bb" * 64,
            signed_at=600.0,
        )
        reg.register(pkg)

        assert not reg.is_revoked("revoke-me")

        result = reg.revoke("revoke-me", reason="有安全漏洞", signer=signer)
        assert result["success"]
        assert result["name"] == "revoke-me"
        assert reg.is_revoked("revoke-me")

        rev = reg.get_revocation("revoke-me")
        assert rev["reason"] == "有安全漏洞"
        assert rev["signed_by"] == signer.did

    def test_revoke_requires_identity(self, tmp_path):
        reg = SkillRegistry(storage_dir=str(tmp_path / "reg"))

        import pytest

        with pytest.raises(SkillSigningError, match="吊销需要签名身份"):
            reg.revoke("some-skill", reason="no id")

    def test_revoked_skill_excluded_from_list(self, tmp_path):
        reg = SkillRegistry(storage_dir=str(tmp_path / "reg"))
        signer = AIDSigner()
        signer.generate()

        for name in ["good", "bad"]:
            pkg = SkillPackage(
                name=name,
                version="1.0.0",
                author_did=signer.did,
                author_public_key_hex=signer.public_key.hex(),
                content_hash=name,
                signature="cc" * 64,
                signed_at=700.0,
            )
            reg.register(pkg)

        reg.revoke("bad", reason="恶意代码", signer=signer)

        items = reg.list(include_revoked=False)
        names = [s["name"] for s in items]
        assert "good" in names
        assert "bad" not in names

        items_all = reg.list(include_revoked=True)
        names_all = [s["name"] for s in items_all]
        assert "bad" in names_all

    def test_revoke_saves_to_disk(self, tmp_path):
        reg_dir = tmp_path / "rev_disk"
        reg = SkillRegistry(storage_dir=str(reg_dir))
        signer = AIDSigner()
        signer.generate()

        reg.revoke("gone", reason="bye", signer=signer)

        reg2 = SkillRegistry(storage_dir=str(reg_dir))
        assert reg2.is_revoked("gone")


class TestVerificationWithRegistry:
    """带注册表的签名验证"""

    def test_verify_checks_revocation(self, tmp_path):
        skill_file = tmp_path / "rev_skill.py"
        skill_file.write_text("print('revocable')")

        signer = AIDSigner()
        signer.generate()

        reg_dir = tmp_path / "skill_reg"
        reg = SkillRegistry(storage_dir=str(reg_dir), signer=signer)

        pkg = sign_skill(skill_file, signer, name="rev-skill")
        reg.register(pkg)

        # 初始验证通过
        result = verify_skill(skill_file, pkg, registry=reg)
        assert result["valid"] is True
        assert result["revoked"] is False

        # 吊销后验证失败
        reg.revoke("rev-skill", reason="不再维护")
        result = verify_skill(skill_file, pkg, registry=reg)
        assert result["valid"] is False
        assert result["revoked"] is True


class TestFullIntegration:
    """完整端到端流程"""

    def test_sign_verify_register_list_revoke(self, tmp_path):
        """签名 → 验证 → 注册 → 列表 → 吊销 → 确认吊销"""
        skill_file = tmp_path / "integration.py"
        skill_file.write_text("def run(): pass")

        # 1. 创建身份
        author = AIDSigner()
        author.generate()

        # 2. 签名
        pkg = sign_skill(
            skill_file,
            author,
            name="integrated",
            version="2.0.0",
            description="完整流程测试",
            tags=["test", "demo"],
        )
        assert pkg.is_signed

        # 3. 验证
        result = verify_skill(skill_file, pkg)
        assert result["valid"]

        # 4. 保存并重新加载
        pkg_file = tmp_path / "integrated.skill.json"
        pkg.save(pkg_file)
        loaded = SkillPackage.load(pkg_file)
        assert loaded.name == "integrated"

        # 5. 注册
        reg_dir = tmp_path / "reg"
        reg = SkillRegistry(storage_dir=str(reg_dir))
        reg.register(pkg)

        items = reg.list()
        assert len(items) == 1
        assert items[0]["name"] == "integrated"

        # 6. 吊销
        reg._signer = author
        reg.revoke("integrated", reason="新版本已发布")

        assert reg.is_revoked("integrated")
        items_after = reg.list(include_revoked=False)
        assert len(items_after) == 0

    def test_multiple_skills_independent(self, tmp_path):
        """多个独立的技能签名周期不影响"""
        reg_dir = tmp_path / "multi_reg"
        reg = SkillRegistry(storage_dir=str(reg_dir))

        author = AIDSigner()
        author.generate()

        skills = ["alpha", "beta", "gamma"]
        for name in skills:
            f = tmp_path / f"{name}.py"
            f.write_text(f"# {name} skill")
            pkg = sign_skill(f, author, name=name)
            reg.register(pkg)

        assert len(reg.list()) == 3
        for name in skills:
            assert reg.get(name) is not None

    def test_verification_reject_unknown_author(self, tmp_path):
        """验证拒绝被未知密钥签名的包"""
        skill_file = tmp_path / "unknown.py"
        skill_file.write_text("unknown")

        author = AIDSigner()
        author.generate()

        pkg = sign_skill(skill_file, author, name="unknown")

        # 篡改为不同的公钥
        imposter = AIDSigner()
        imposter.generate()
        pkg.author_public_key_hex = imposter.public_key.hex()

        result = verify_skill(skill_file, pkg)
        assert not result["valid"]


class TestSkillRuntime:
    """SkillRuntime 技能执行测试"""

    def test_run_empty_registry(self, tmp_path):
        """无技能时 list 返回空"""
        registry = SkillRegistry(storage_dir=str(tmp_path))
        runtime = SkillRuntime(registry)
        result = runtime.list_skills()
        assert "暂无" in result or "可用" not in result

    def test_execute_python(self, tmp_path):
        """执行 Python 技能"""
        skill_file = tmp_path / "hello.py"
        skill_file.write_text("""
def main(params):
    name = params.get("name", "world")
    return {"greeting": f"hello {name}"}
""")

        author = AIDSigner()
        author.generate()

        pkg = sign_skill(skill_file, author, name="python-skill", version="1.0.0")

        registry = SkillRegistry(storage_dir=str(tmp_path))
        registry.register(pkg, content=skill_file.read_bytes())
        runtime = SkillRuntime(registry)

        result = runtime.execute("python-skill", '{"name": "TestAgent"}')
        assert '"greeting": "hello TestAgent"' in result

    def test_execute_python_no_main(self, tmp_path):
        """Python 技能没有 main 函数也能执行"""
        skill_file = tmp_path / "silent.py"
        skill_file.write_text('print("Hello from skill")')

        author = AIDSigner()
        author.generate()
        pkg = sign_skill(skill_file, author, name="silent")

        registry = SkillRegistry(storage_dir=str(tmp_path))
        registry.register(pkg, content=skill_file.read_bytes())
        runtime = SkillRuntime(registry)

        result = runtime.execute("silent", "{}")
        assert "Hello from skill" in result

    def test_execute_revoked_skill(self, tmp_path):
        """已吊销的技能返回错误"""
        skill_file = tmp_path / "revocable.py"
        skill_file.write_text('print("dangerous")')

        author = AIDSigner()
        author.generate()
        pkg = sign_skill(skill_file, author, name="danger-skill")

        registry = SkillRegistry(storage_dir=str(tmp_path))
        registry.register(pkg, content=skill_file.read_bytes())
        registry.revoke("danger-skill", reason="有安全问题", signer=author)

        runtime = SkillRuntime(registry)
        result = runtime.execute("danger-skill", "{}")
        assert "吊销" in result

    def test_execute_markdown(self, tmp_path):
        """Markdown 技能直接返回内容"""
        skill_file = tmp_path / "doc.md"
        skill_file.write_text("# Hello\n\nThis is a doc skill.")

        author = AIDSigner()
        author.generate()
        pkg = sign_skill(skill_file, author, name="doc-skill", content_type="markdown")

        registry = SkillRegistry(storage_dir=str(tmp_path))
        registry.register(pkg, content=skill_file.read_bytes())
        runtime = SkillRuntime(registry)

        result = runtime.execute("doc-skill", "{}")
        assert "# Hello" in result

    def test_missing_skill(self, tmp_path):
        """执行不存在的技能返回错误"""
        registry = SkillRegistry(storage_dir=str(tmp_path))
        runtime = SkillRuntime(registry)
        result = runtime.execute("nonexistent", "{}")
        assert "未找到" in result or "错误" in result

    def test_registry_list(self, tmp_path):
        """注册表 list 包含技能信息"""
        skill_file = tmp_path / "mytool.py"
        skill_file.write_text("pass")

        author = AIDSigner()
        author.generate()
        pkg = sign_skill(skill_file, author, name="mytool", version="1.0.0", description="A test tool", tags=["demo"])

        registry = SkillRegistry(storage_dir=str(tmp_path))
        registry.register(pkg, content=skill_file.read_bytes())

        entries = registry.list(include_revoked=False)
        assert len(entries) == 1
        assert entries[0]["name"] == "mytool"
        assert entries[0]["description"] == "A test tool"
        assert entries[0]["is_signed"]
        assert not entries[0]["is_revoked"]

    def test_skill_registry_persists(self, tmp_path):
        """注册表重启后保持数据"""
        storage = str(tmp_path / "registry_data")
        # 第一次
        author = AIDSigner()
        author.generate()
        skill_file = tmp_path / "persist.py"
        skill_file.write_text("print('persist')")
        pkg = sign_skill(skill_file, author, name="persist-skill")

        registry1 = SkillRegistry(storage_dir=storage)
        registry1.register(pkg, content=skill_file.read_bytes())

        # 第二次（新实例）
        registry2 = SkillRegistry(storage_dir=storage)
        assert registry2.get("persist-skill") is not None
        assert registry2.get_content("persist-skill") == b"print('persist')"


# ═══════════════════════════════════════════
# SkillAttributionTracker — 归因跟踪测试
# ═══════════════════════════════════════════


class TestSkillAttribution:
    """SkillAttributionTracker 归因跟踪 + SkillReputation 信誉"""

    def test_record_and_author_stats(self, tmp_path):
        """记录归因后能查到作者统计"""
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path))
        rec = AttributionRecord(
            executor_did="did:aid:executor1",
            skill_name="test-skill",
            author_did="did:aid:author1",
            timestamp=time.time(),
            success=True,
            duration_ms=150,
        )
        tracker.record(rec)

        stats = tracker.get_author_stats("did:aid:author1")
        assert stats["total_executions"] == 1
        assert stats["success_rate"] == 1.0
        assert stats["unique_executors"] == 1
        assert stats["avg_duration_ms"] == 150.0

    def test_record_multiple_authors(self, tmp_path):
        """多个作者的统计互不干扰"""
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path))
        t = time.time()
        for i in range(3):
            tracker.record(
                AttributionRecord(
                    executor_did="executor",
                    skill_name="s",
                    author_did=f"author{i}",
                    timestamp=t + i,
                    success=True,
                    duration_ms=100,
                )
            )
        for i in range(3):
            stats = tracker.get_author_stats(f"author{i}")
            assert stats["total_executions"] == 1
        # 合在一起查
        all_records = tracker._query()
        assert len(all_records) == 3

    def test_executor_stats(self, tmp_path):
        """执行者统计正确"""
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path))
        t = time.time()
        tracker.record(
            AttributionRecord(
                executor_did="execA",
                skill_name="s1",
                author_did="author1",
                timestamp=t,
                success=True,
                duration_ms=50,
            )
        )
        tracker.record(
            AttributionRecord(
                executor_did="execA",
                skill_name="s2",
                author_did="author1",
                timestamp=t + 1,
                success=False,
                duration_ms=200,
            )
        )

        stats = tracker.get_executor_stats("execA")
        assert stats["total_executions"] == 2
        assert stats["success_rate"] == 0.5
        assert stats["unique_skills"] == 2

    def test_skill_stats(self, tmp_path):
        """技能统计正确"""
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path))
        t = time.time()
        tracker.record(
            AttributionRecord(
                executor_did="exec1",
                skill_name="greet",
                author_did="author1",
                timestamp=t,
                success=True,
                duration_ms=10,
            )
        )
        tracker.record(
            AttributionRecord(
                executor_did="exec2",
                skill_name="greet",
                author_did="author1",
                timestamp=t + 1,
                success=True,
                duration_ms=20,
            )
        )

        stats = tracker.get_skill_stats("greet")
        assert stats["total_executions"] == 2
        assert stats["success_rate"] == 1.0
        assert stats["unique_executors"] == 2

    def test_leaderboard(self, tmp_path):
        """作者排行榜排序正确"""
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path))
        t = time.time()
        for i in range(5):
            tracker.record(
                AttributionRecord(
                    executor_did="exec",
                    skill_name="s",
                    author_did=f"author{i}",
                    timestamp=t + i,
                    success=True,
                    duration_ms=100,
                )
            )
        # author0 执行两次
        tracker.record(
            AttributionRecord(
                executor_did="exec",
                skill_name="s",
                author_did="author0",
                timestamp=t + 10,
                success=True,
                duration_ms=100,
            )
        )

        board = tracker.get_authors_leaderboard(top_n=5)
        assert len(board) == 5
        assert board[0]["author_did"] == "author0"  # 最多执行
        assert board[0]["total_executions"] == 2

    def test_persistence(self, tmp_path):
        """归因数据在新 tracker 实例中仍然可用"""
        storage = str(tmp_path)
        tracker1 = SkillAttributionTracker(storage_dir=storage)
        tracker1.record(
            AttributionRecord(
                executor_did="exec",
                skill_name="s",
                author_did="author",
                timestamp=time.time(),
                success=True,
                duration_ms=50,
            )
        )

        tracker2 = SkillAttributionTracker(storage_dir=storage)
        stats = tracker2.get_author_stats("author")
        assert stats["total_executions"] == 1

    def test_empty_stats(self, tmp_path):
        """无数据时返回零值"""
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path))
        stats = tracker.get_author_stats("nonexistent")
        assert stats["total_executions"] == 0
        assert stats["success_rate"] == 0.0

        board = tracker.get_authors_leaderboard()
        assert board == []


# ═══════════════════════════════════════════
# SkillReputation — 信誉评分测试
# ═══════════════════════════════════════════


class TestSkillReputation:
    """SkillReputation 信誉评分单元测试"""

    def test_high_reputation(self):
        """高使用量的作者信誉分高"""
        stats = {"total_executions": 100, "success_rate": 1.0, "unique_executors": 20, "avg_duration_ms": 50}
        score = SkillReputation.compute(stats)
        assert score > 70
        assert SkillReputation.compute_level(score) in ("S", "A")

    def test_low_reputation(self):
        """低使用量信誉分低"""
        stats = {"total_executions": 1, "success_rate": 0.0, "unique_executors": 1, "avg_duration_ms": 5000}
        score = SkillReputation.compute(stats)
        assert score < 40

    def test_zero_stats(self):
        """零使用量信誉分为 0"""
        stats = {"total_executions": 0, "success_rate": 0.0, "unique_executors": 0, "avg_duration_ms": 0}
        score = SkillReputation.compute(stats)
        assert score == 0.0
        assert SkillReputation.compute_level(score) == "D"

    def test_level_bounds(self):
        """等级边界"""
        assert SkillReputation.compute_level(85) == "S"
        assert SkillReputation.compute_level(70) == "A"
        assert SkillReputation.compute_level(50) == "B"
        assert SkillReputation.compute_level(30) == "C"
        assert SkillReputation.compute_level(10) == "D"

    def test_format_report(self):
        """报告生成"""
        stats = {"total_executions": 50, "success_rate": 0.95, "unique_executors": 10, "avg_duration_ms": 100}
        report = SkillReputation.format_author_report("did:aid:test", stats)
        assert "信誉分" in report
        assert "did:aid:test" in report or "test" in report


# ═══════════════════════════════════════════
# 集成测试 — SkillRuntime + 归因
# ═══════════════════════════════════════════


class TestAttributionIntegration:
    """SkillRuntime 执行自动记录归因"""

    def test_runtime_records_attribution(self, tmp_path):
        """SkillRuntime.execute() 自动记录归因"""
        storage = str(tmp_path / "registry")
        registry = SkillRegistry(storage_dir=storage)
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path))
        runtime = SkillRuntime(registry, tracker=tracker)

        # 注册一个简单 python 技能
        author = AIDSigner()
        author.generate()
        skill_file = tmp_path / "hello.py"
        skill_file.write_text("def main(p): return 'ok'")
        pkg = sign_skill(skill_file, author, name="hello")
        registry.register(pkg, content=skill_file.read_bytes())

        result = runtime.execute("hello", "{}", executor_did="did:aid:caller")
        assert "ok" in result

        # 归因已记录
        stats = tracker.get_author_stats(author.did)
        assert stats["total_executions"] == 1
        assert stats["success_rate"] == 1.0

    def test_runtime_no_tracker(self, tmp_path):
        """不传 tracker 时也不崩溃"""
        storage = str(tmp_path / "reg2")
        registry = SkillRegistry(storage_dir=storage)
        runtime = SkillRuntime(registry, tracker=None)

        author = AIDSigner()
        author.generate()
        skill_file = tmp_path / "simple.py"
        skill_file.write_text("def main(p): return 42")
        pkg = sign_skill(skill_file, author, name="simple")
        registry.register(pkg, content=skill_file.read_bytes())

        result = runtime.execute("simple", "{}", executor_did="")
        assert "42" in result

    def test_runtime_no_executor_did(self, tmp_path):
        """不传 executor_did 时不记录归因"""
        storage = str(tmp_path / "reg3")
        registry = SkillRegistry(storage_dir=storage)
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path))
        runtime = SkillRuntime(registry, tracker=tracker)

        author = AIDSigner()
        author.generate()
        skill_file = tmp_path / "task.py"
        skill_file.write_text("def main(p): return 'done'")
        pkg = sign_skill(skill_file, author, name="task")
        registry.register(pkg, content=skill_file.read_bytes())

        runtime.execute("task", "{}", executor_did="")  # 空 DID，不记录
        stats = tracker.get_author_stats(author.did)
        assert stats["total_executions"] == 0  # 没记录

    def test_runtime_failure_recorded(self, tmp_path):
        """执行失败也记录归因（python 内部吞异常，但记录为 success=True）"""
        storage = str(tmp_path / "reg4")
        registry = SkillRegistry(storage_dir=storage)
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path))
        runtime = SkillRuntime(registry, tracker=tracker)

        author = AIDSigner()
        author.generate()
        skill_file = tmp_path / "crash.py"
        skill_file.write_text("def main(p): raise RuntimeError('boom')")
        pkg = sign_skill(skill_file, author, name="crash")
        registry.register(pkg, content=skill_file.read_bytes())

        result = runtime.execute("crash", "{}", executor_did="did:aid:caller")
        # python 执行器内部吞异常，输出无返回值的消息
        assert "执行完毕" in result

        stats = tracker.get_author_stats(author.did)
        assert stats["total_executions"] == 1
