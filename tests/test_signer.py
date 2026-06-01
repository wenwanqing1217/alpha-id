"""
AIDSigner SDK 单元测试
"""

import pytest
from alpha_id import AIDSigner


class TestAIDSigner:
    """AIDSigner SDK 签名/验签"""

    def test_generate_identity(self):
        signer = AIDSigner()
        did = signer.generate()
        assert did.startswith("did:aid:")
        assert len(did) > 10
        assert signer.has_identity
        assert signer.did == did

    def test_sign_and_verify(self):
        signer = AIDSigner()
        signer.generate()
        payload = b"hello world"
        sig = signer.sign(payload)
        assert len(sig) == 64
        assert signer.verify(payload, sig)

    def test_verify_wrong_payload(self):
        signer = AIDSigner()
        signer.generate()
        sig = signer.sign(b"good data")
        assert not signer.verify(b"bad data", sig)

    def test_verify_wrong_key(self):
        s1, s2 = AIDSigner(), AIDSigner()
        s1.generate()
        s2.generate()
        sig = s1.sign(b"hello")
        assert not s2.verify(b"hello", sig)

    def test_sign_file(self, tmp_path):
        signer = AIDSigner()
        signer.generate()
        f = tmp_path / "test.txt"
        f.write_bytes(b"file content")
        sig = signer.sign_file(str(f))
        assert len(sig) == 64
        assert (tmp_path / "test.txt.sig").exists()
        assert signer.verify_file(str(f))
        # 修改文件 → 验证失败
        f.write_bytes(b"tampered")
        assert not signer.verify_file(str(f))

    def test_sign_json(self):
        signer = AIDSigner()
        signer.generate()
        obj = {"name": "agent", "version": 1}
        sig = signer.sign_json(obj)
        assert signer.verify_json(obj, sig)

        # 验证序不同的 JSON 也能通过（sort_keys）
        obj2 = {"version": 1, "name": "agent"}
        assert signer.verify_json(obj2, sig)

    def test_sign_json_tampered(self):
        signer = AIDSigner()
        signer.generate()
        obj = {"name": "agent", "version": 1}
        sig = signer.sign_json(obj)
        assert not signer.verify_json({"name": "hacker", "version": 1}, sig)

    def test_export_import_keys(self):
        signer = AIDSigner()
        signer.generate()
        priv = signer.export_private_key()
        pub = signer.export_public_key()
        assert len(priv) == 32
        assert len(pub) == 32

        # 从私钥恢复
        s2 = AIDSigner()
        s2.load_private_key_from_bytes(priv)
        assert s2.did == signer.did
        assert s2.public_key == pub

    def test_did_document(self):
        signer = AIDSigner()
        signer.generate()
        doc = signer.build_document()
        assert doc.id == signer.did
        assert len(doc.verification_method) == 1
        assert doc.authentication == [f"{signer.did}#key-1"]

    def test_aid_directory(self, tmp_path):
        signer = AIDSigner()
        signer.generate()
        aid_dir = tmp_path / ".aid"
        result = signer.save_to_aid_dir(str(aid_dir))
        assert result["did"] == signer.did

        # 重新加载
        s2 = AIDSigner()
        did2 = s2.load_from_aid_dir(str(aid_dir))
        assert did2 == signer.did
        assert s2.public_key == signer.public_key

    def test_no_identity_raises(self):
        signer = AIDSigner()
        with pytest.raises(ValueError, match="No private key"):
            signer.sign(b"test")
        with pytest.raises(ValueError, match="No public key"):
            signer.verify(b"test", b"x" * 64)
        with pytest.raises(ValueError, match="No private key"):
            signer.export_private_key()

    def test_verify_with_explicit_key(self):
        s1, s2 = AIDSigner(), AIDSigner()
        s1.generate()
        s2.generate()
        sig = s1.sign(b"cross verify")
        # 用 s1 的公钥显式验证
        assert s2.verify(b"cross verify", sig, public_key=s1.public_key)
        # 没有身份也能验
        s3 = AIDSigner()
        assert s3.verify(b"cross verify", sig, public_key=s1.public_key)
