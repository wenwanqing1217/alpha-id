"""Tests for DIDResolver and SkillRepository (P3-2 Decentralized Protocol)"""

from pathlib import Path

import pytest

from alpha_id.did_resolver import DIDResolver
from alpha_id.signer import AIDSigner
from alpha_id.skill_repository import (
    REPOSITORY_META_FILE,
    SKILLS_DIR,
    RepositoryMeta,
    SkillRepository,
)
from alpha_id.skill_signer import SkillRegistry, SkillRuntime


class TestDIDResolver:
    def test_resolve_from_public_key(self):
        signer = AIDSigner()
        signer.generate()
        pk = signer.public_key

        resolver = DIDResolver()
        doc = resolver.resolve_from_public_key(pk)
        assert doc.id.startswith("did:aid:")
        assert len(doc.verification_method) == 1
        vm = doc.verification_method[0]
        assert vm["type"] == "Ed25519VerificationKey2018"
        assert vm["controller"] == doc.id

    def test_resolve_with_key_hex(self):
        signer = AIDSigner()
        signer.generate()

        resolver = DIDResolver()
        doc = resolver.resolve_with_key(signer.did, signer.public_key.hex())
        assert doc is not None
        assert doc.id == signer.did

    def test_resolve_invalid_did_returns_none(self):
        resolver = DIDResolver()
        assert resolver.resolve("did:other:xxx") is None
        assert resolver.resolve("not-a-did") is None

    def test_verify_did_matches_key(self):
        signer = AIDSigner()
        signer.generate()
        assert DIDResolver.verify_did(signer.did, signer.public_key)
        signer2 = AIDSigner()
        signer2.generate()
        assert not DIDResolver.verify_did(signer.did, signer2.public_key)

    def test_resolve_local_aid_dir(self, tmp_path, monkeypatch):
        aid_dir = tmp_path / ".aid"
        aid_dir.mkdir()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        signer = AIDSigner()
        signer.generate()
        (aid_dir / "identity.did").write_text(signer.did)
        doc = signer._reg.build_document()
        (aid_dir / "identity.doc.json").write_text(doc.to_json())

        DIDResolver.clear_cache()
        resolver = DIDResolver()
        resolved = resolver.resolve(signer.did)
        assert resolved is not None
        assert resolved.id == signer.did

    def test_cache_hits(self):
        signer = AIDSigner()
        signer.generate()
        resolver = DIDResolver()
        doc1 = resolver.resolve_from_public_key(signer.public_key)
        doc2 = resolver.resolve(signer.did)
        assert doc2 is not None
        assert doc2.id == doc1.id


class TestSkillRepository:
    def test_init_repo(self, tmp_path):
        repo = SkillRepository()
        meta = repo.init_repo(tmp_path / "my-skills", name="My Skills")
        assert meta.name == "My Skills"
        assert (tmp_path / "my-skills" / REPOSITORY_META_FILE).exists()
        assert (tmp_path / "my-skills" / SKILLS_DIR).is_dir()

    def test_scan_empty_repo(self, tmp_path):
        repo = SkillRepository()
        repo.init_repo(tmp_path / "empty-repo", name="Empty")
        skills = repo.scan(tmp_path / "empty-repo")
        assert skills == []

    def test_publish_and_scan(self, tmp_path):
        signer = AIDSigner()
        signer.generate()

        repo_path = tmp_path / "skill-repo"
        repo = SkillRepository()
        repo.init_repo(repo_path, name="Test Repo", author_did=signer.did)

        skill_file = tmp_path / "hello.py"
        skill_file.write_text("def main(p): return 'hello from repo'")

        skill = repo.publish_skill(
            repo_path,
            skill_file,
            signer,
            name="hello",
            version="1.0.0",
            description="A test skill",
        )
        assert skill.name == "hello"
        assert skill.is_signed
        assert skill.skill_file.exists()
        assert skill.package_file.exists()

        skills = repo.scan(repo_path)
        assert len(skills) == 1
        assert skills[0].name == "hello"
        assert skills[0].is_signed

    def test_install_to_registry(self, tmp_path):
        signer = AIDSigner()
        signer.generate()

        repo_path = tmp_path / "src-repo"
        repo = SkillRepository()
        repo.init_repo(repo_path, name="Source", author_did=signer.did)
        skill_file = tmp_path / "greet.py"
        skill_file.write_text("def main(p): return 'hi'")
        published = repo.publish_skill(repo_path, skill_file, signer, name="greet")

        registry = SkillRegistry(storage_dir=str(tmp_path / "registry"))
        result = repo.install_skill(published, registry)
        assert result["success"]

        runtime = SkillRuntime(registry)
        output = runtime.execute("greet", "{}", executor_did=signer.did)
        assert "hi" in output

    def test_publish_force_overwrites(self, tmp_path):
        signer = AIDSigner()
        signer.generate()
        repo_path = tmp_path / "overwrite-repo"
        repo = SkillRepository()
        repo.init_repo(repo_path, name="Overwrite")

        skill_file = tmp_path / "ver.py"
        skill_file.write_text("v1")
        repo.publish_skill(repo_path, skill_file, signer, name="ver")

        skill_file.write_text("v2")
        repo.publish_skill(repo_path, skill_file, signer, name="ver", force=True)
        skills = repo.scan(repo_path)
        assert len(skills) == 1

    def test_publish_without_force_raises(self, tmp_path):
        signer = AIDSigner()
        signer.generate()
        repo_path = tmp_path / "no-force"
        repo = SkillRepository()
        repo.init_repo(repo_path, name="NoForce")

        skill_file = tmp_path / "dup.py"
        skill_file.write_text("dup")
        repo.publish_skill(repo_path, skill_file, signer, name="dup")
        with pytest.raises(FileExistsError):
            repo.publish_skill(repo_path, skill_file, signer, name="dup")

    def test_get_repo_meta(self, tmp_path):
        signer = AIDSigner()
        signer.generate()
        repo_path = tmp_path / "meta-test"
        repo = SkillRepository()
        repo.init_repo(repo_path, name="MetaTest", author_did=signer.did)

        meta = repo.get_repo_meta(repo_path)
        assert meta is not None
        assert meta.name == "MetaTest"
        assert meta.author_did == signer.did

    def test_scan_nonexistent(self, tmp_path):
        repo = SkillRepository()
        skills = repo.scan(tmp_path / "nonexistent")
        assert skills == []

    def test_repository_meta_roundtrip(self, tmp_path):
        meta = RepositoryMeta(name="Test", description="Desc", author_did="did:aid:test")
        json_str = meta.to_json()
        restored = RepositoryMeta.from_json(json_str)
        assert restored.name == "Test"
        assert restored.author_did == "did:aid:test"

    def test_multiple_skills_in_one_repo(self, tmp_path):
        signer = AIDSigner()
        signer.generate()
        repo_path = tmp_path / "multi"
        repo = SkillRepository()
        repo.init_repo(repo_path, name="Multi", author_did=signer.did)

        for name in ["skill-a", "skill-b", "skill-c"]:
            sf = tmp_path / ("%s.py" % name)
            sf.write_text("def main(p): return 'ok'")
            repo.publish_skill(repo_path, sf, signer, name=name)

        skills = repo.scan(repo_path)
        names = sorted(s.name for s in skills)
        assert names == ["skill-a", "skill-b", "skill-c"]
