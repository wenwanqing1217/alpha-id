"""
CoreDID & DIDDocument 单元测试
"""

import json
import pytest
from core.did import CoreDID, DIDDocument, _b58encode


class TestB58Encode:
    """Base58 编码测试"""

    def test_encode_zero(self):
        """输入空字节应返回 B58 首位字符"""
        result = _b58encode(b"")
        assert isinstance(result, str) and len(result) == 1

    def test_encode_small_number(self):
        """小数字编码"""
        assert _b58encode(b"\x01") == "2"  # 1→"2"

    def test_encode_known_bytes(self):
        """已知字节串编码"""
        result = _b58encode(b"hello")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_deterministic(self):
        """相同输入应产生相同输出"""
        data = b"test data for deterministic encoding"
        assert _b58encode(data) == _b58encode(data)


class TestDIDDocument:
    """DIDDocument 数据类测试"""

    def test_to_json_roundtrip(self):
        """to_json → from_json 应恢复原始对象"""
        doc = DIDDocument(
            id="did:aid:test123",
            verification_method=[{"id": "did:aid:test123#key-1", "type": "Ed25519VerificationKey2018"}],
            authentication=["did:aid:test123#key-1"],
            service=[{"id": "did:aid:test123#hub", "type": "DIDComm", "serviceEndpoint": "https://hub.example.com"}],
        )
        json_str = doc.to_json()
        restored = DIDDocument.from_json(json_str)
        assert restored.id == doc.id
        assert restored.verification_method == doc.verification_method
        assert restored.authentication == doc.authentication
        assert restored.service == doc.service

    def test_from_json_minimal(self):
        """最小化 JSON 应正确反序列化"""
        json_str = '{"id": "did:aid:minimal", "verification_method": [], "authentication": [], "service": []}'
        doc = DIDDocument.from_json(json_str)
        assert doc.id == "did:aid:minimal"
        assert doc.verification_method == []
        assert doc.authentication == []


class TestCoreDID:
    """CoreDID 核心功能测试"""

    def test_generate_creates_valid_did(self):
        """generate() 应产生有效的 did:aid: 标识符"""
        did_obj = CoreDID.generate()
        assert did_obj.did is not None
        assert did_obj.did.startswith("did:aid:")

    def test_generate_creates_private_key(self):
        """generate() 应创建私钥"""
        did_obj = CoreDID.generate()
        assert did_obj._private_key is not None

    def test_generate_public_key_not_none(self):
        """generate() 后 public_key 不应为空"""
        did_obj = CoreDID.generate()
        assert did_obj.public_key is not None
        assert len(did_obj.public_key) > 0

    def test_generate_unique_dids(self):
        """多次 generate 应产生不同的 DID"""
        did1 = CoreDID.generate()
        did2 = CoreDID.generate()
        assert did1.did != did2.did

    def test_default_did_is_none(self):
        """未 generate 时应返回 None"""
        did_obj = CoreDID()
        assert did_obj.did is None
        assert did_obj.public_key is None

    def test_sign_and_verify(self):
        """签名后验证应返回 True"""
        did_obj = CoreDID.generate()
        payload = b"test message for signing"
        signature = did_obj.sign(payload)
        assert isinstance(signature, bytes)
        assert len(signature) > 0
        # 验证
        pub_bytes = did_obj.public_key
        assert CoreDID.verify(pub_bytes, payload, signature) is True

    def test_verify_wrong_message(self):
        """错误消息验证应返回 False"""
        did_obj = CoreDID.generate()
        payload = b"correct message"
        wrong_payload = b"wrong message"
        signature = did_obj.sign(payload)
        pub_bytes = did_obj.public_key
        assert CoreDID.verify(pub_bytes, wrong_payload, signature) is False

    def test_verify_bad_signature(self):
        """篡改签名验证应返回 False"""
        did_obj = CoreDID.generate()
        payload = b"test message"
        signature = did_obj.sign(payload)
        pub_bytes = did_obj.public_key
        # 篡改签名
        bad_sig = b"\x00" * len(signature)
        assert CoreDID.verify(pub_bytes, bad_sig, payload) is False

    def test_build_document(self):
        """build_document 应返回有效的 DIDDocument"""
        did_obj = CoreDID.generate()
        doc = did_obj.build_document()
        assert isinstance(doc, DIDDocument)
        assert doc.id == did_obj.did
        assert len(doc.verification_method) == 1
        assert len(doc.authentication) == 1
        # verification_method 应包含正确的 key ID
        key_id = doc.verification_method[0]["id"]
        assert key_id == did_obj.did + "#key-1"

    def test_build_document_before_generate_raises(self):
        """未 generate 时 build_document 应抛 ValueError"""
        did_obj = CoreDID()
        with pytest.raises(ValueError, match="DID not initialized"):
            did_obj.build_document()

    def test_sign_before_generate_raises(self):
        """未 generate 时 sign 应抛 ValueError"""
        did_obj = CoreDID()
        with pytest.raises(ValueError, match="DID not initialized"):
            did_obj.sign(b"test")

    def test_did_matches_key(self):
        """did_matches_key 应识别匹配的 DID"""
        did_obj = CoreDID.generate()
        pub_bytes = did_obj.public_key
        assert CoreDID.did_matches_key(did_obj.did, pub_bytes) is True

    def test_did_matches_key_wrong_did(self):
        """错误 DID 应返回 False"""
        did_obj = CoreDID.generate()
        wrong_did = "did:aid:1111111111111111111111111111"
        pub_bytes = did_obj.public_key
        assert CoreDID.did_matches_key(wrong_did, pub_bytes) is False

    def test_did_matches_key_wrong_prefix(self):
        """非 did:aid: 前缀应返回 False"""
        did_obj = CoreDID.generate()
        pub_bytes = did_obj.public_key
        assert CoreDID.did_matches_key("did:eth:abc123", pub_bytes) is False

    def test_verify_public_key_length(self):
        """Ed25519 公钥应为 32 字节"""
        did_obj = CoreDID.generate()
        assert len(did_obj.public_key) == 32

    def test_verify_document_has_valid_json(self):
        """DIDDocument.to_json 应产生合法 JSON"""
        did_obj = CoreDID.generate()
        doc = did_obj.build_document()
        parsed = json.loads(doc.to_json())
        assert parsed["id"] == did_obj.did
        assert "verification_method" in parsed

    def test_sign_deterministic(self):
        """同一私钥对相同消息签名应一致（Ed25519 是确定性的）"""
        did_obj = CoreDID.generate()
        payload = b"deterministic test"
        sig1 = did_obj.sign(payload)
        sig2 = did_obj.sign(payload)
        assert sig1 == sig2

    def test_multiple_sign_verify_roundtrip(self):
        """多次签名-验证循环应全部通过"""
        did_obj = CoreDID.generate()
        pub_bytes = did_obj.public_key
        messages = [b"msg1", b"msg2", b"msg3", b"a longer message with more content"]
        for msg in messages:
            sig = did_obj.sign(msg)
            assert CoreDID.verify(pub_bytes, msg, sig) is True

    def test_cross_did_verify_fails(self):
        """DID-A 签名的消息不应被 DID-B 的密钥验证通过"""
        did_a = CoreDID.generate()
        did_b = CoreDID.generate()
        payload = b"cross did test"
        signature = did_a.sign(payload)
        pub_b = did_b.public_key
        assert CoreDID.verify(pub_b, payload, signature) is False

    def test_verify_none_public_key(self):
        """传入无效公钥不应抛异常"""
        # 空字节串作为公钥
        result = CoreDID.verify(b"", b"test", b"signature")
        assert result is False

    def test_did_matches_key_self_consistency(self):
        """generate→public_key→did_matches_key 内循环验证"""
        did_obj = CoreDID.generate()
        pub = did_obj.public_key
        assert CoreDID.did_matches_key(did_obj.did, pub) is True
        # 稍微修改公钥字节，应返回 False
        tampered = bytearray(pub)
        tampered[0] ^= 0xFF
        assert CoreDID.did_matches_key(did_obj.did, bytes(tampered)) is False

    def test_build_document_includes_pubkey(self):
        """DIDDocument 的 verificationMethod 应包含可解码的公钥"""
        did_obj = CoreDID.generate()
        doc = did_obj.build_document()
        pubkey_multibase = doc.verification_method[0]["publicKeyMultibase"]
        assert pubkey_multibase.startswith("z")
        # 解码后应有意义（Base58 解码长度）
        decoded_raw = pubkey_multibase[1:]  # 去掉 "z" 前缀
        assert len(decoded_raw) > 30  # Base58 编码的 32 字节公钥
