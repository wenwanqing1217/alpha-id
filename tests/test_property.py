"""
属性测试 — 基于 hypothesis 的 property-based testing

覆盖加密/解密、向量搜索、配置等模块的边界情况。
与示例测试不同，hypothesis 自动生成大量随机输入来发现边界 bug。
"""

import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import integers, lists, text

# 确保测试环境
os.environ.setdefault("AUTH_MASTER_KEY", "test-master-key-for-pytest-0123456789abcdef")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.dual_chain import (
    PRIVACY_THRESHOLD,
    DualChainManager,
    _decrypt,
    _derive_key,
    _encrypt,
)
from core.secrets import decrypt as secret_decrypt
from core.secrets import decrypt_if_needed
from core.secrets import encrypt as secret_encrypt

# ── 密钥派生属性测试 ──

class TestKeyDerivationProperty:
    """密钥派生的属性测试"""

    @given(did=text(min_size=1, max_size=100))
    @settings(max_examples=50, deadline=None)
    def test_derive_deterministic(self, did):
        """相同 DID + salt 总是派生相同密钥"""
        salt = b"fixed_salt_16byt"
        key1 = _derive_key(did, salt)
        key2 = _derive_key(did, salt)
        assert key1 == key2

    @given(did=text(min_size=1, max_size=100), salt=st.binary(min_size=1, max_size=64))
    @settings(max_examples=50, deadline=None)
    def test_derive_32_bytes(self, did, salt):
        """任意输入都派生 32 字节密钥"""
        key = _derive_key(did, salt)
        assert len(key) == 32

    @given(
        did1=text(min_size=1, max_size=50),
        did2=text(min_size=1, max_size=50),
        salt=st.binary(min_size=16, max_size=32),
    )
    @settings(max_examples=30, deadline=None)
    def test_different_dids_different_keys(self, did1, did2, salt):
        """不同 DID 派生不同密钥（极小概率碰撞除外）"""
        if did1 != did2:
            key1 = _derive_key(did1, salt)
            key2 = _derive_key(did2, salt)
            assert key1 != key2


# ── 加解密属性测试 ──

class TestEncryptionProperty:
    """AES-256-GCM 加解密的属性测试"""

    @given(plaintext=text(min_size=0, max_size=500))
    @settings(max_examples=50, deadline=None)
    def test_encrypt_decrypt_roundtrip(self, plaintext):
        """任意文本加密后解密得到原文"""
        key = _derive_key("did:aid:test", b"fixed_salt_16byt")
        encrypted = _encrypt(plaintext, key)
        decrypted = _decrypt(encrypted, key)
        assert decrypted == plaintext

    @given(plaintext=text(min_size=1, max_size=100))
    @settings(max_examples=30, deadline=None)
    def test_encrypt_produces_different_ciphertext(self, plaintext):
        """相同明文每次加密产生不同密文（nonce 随机）"""
        key = _derive_key("did:aid:test", b"fixed_salt_16byt")
        enc1 = _encrypt(plaintext, key)
        enc2 = _encrypt(plaintext, key)
        assert enc1["ciphertext"] != enc2["ciphertext"]
        assert enc1["nonce"] != enc2["nonce"]

    @given(plaintext=text(min_size=4, max_size=200))
    @settings(max_examples=30, deadline=None)
    def test_ciphertext_does_not_contain_plaintext(self, plaintext):
        """密文不包含明文（仅对足够长的明文验证，避免单字符与十六进制字符碰撞）

        注意：密文是十六进制字符串（字符集 0-9, a-f），单字符明文（如 '0', 'a'）
        天然会出现在十六进制密文中，这是编码特性而非加密漏洞。
        因此只对长度 >= 4 的明文验证，确保明文不会作为完整片段出现在密文中。
        """
        key = _derive_key("did:aid:test", b"fixed_salt_16byt")
        encrypted = _encrypt(plaintext, key)
        assert plaintext not in encrypted["ciphertext"]

    @given(plaintext=text(min_size=1, max_size=100))
    @settings(max_examples=20, deadline=None)
    def test_wrong_key_fails_decryption(self, plaintext):
        """错误密钥解密失败"""
        key1 = _derive_key("did:aid:user_a", b"salt_a_16bytes_")
        key2 = _derive_key("did:aid:user_b", b"salt_b_16bytes_")
        encrypted = _encrypt(plaintext, key1)
        with pytest.raises(Exception):
            _decrypt(encrypted, key2)


# ── 密钥安全模块属性测试 ──

class TestSecretsProperty:
    """secrets 模块的属性测试"""

    @given(plaintext=text(min_size=1, max_size=200))
    @settings(max_examples=30, deadline=None)
    def test_secret_encrypt_decrypt_roundtrip(self, plaintext):
        """ENC[...] 格式加密解密往返"""
        encrypted = secret_encrypt(plaintext)
        assert encrypted.startswith("ENC[")
        assert encrypted.endswith("]")
        decrypted = secret_decrypt(encrypted)
        assert decrypted == plaintext

    @given(plaintext=text(min_size=1, max_size=100))
    @settings(max_examples=20, deadline=None)
    def test_decrypt_if_needed_passthrough(self, plaintext):
        """非 ENC[...] 格式的值原样返回"""
        result = decrypt_if_needed(plaintext)
        assert result == plaintext

    @given(plaintext=text(min_size=1, max_size=50))
    @settings(max_examples=20, deadline=None)
    def test_different_plaintexts_different_ciphertexts(self, plaintext):
        """相同明文每次加密产生不同密文"""
        enc1 = secret_encrypt(plaintext)
        enc2 = secret_encrypt(plaintext)
        assert enc1 != enc2


# ── 双链管理器属性测试 ──

class TestDualChainProperty:
    """双链记忆隔离的属性测试"""

    @pytest.fixture
    def manager(self, tmp_path):
        """临时目录管理器"""
        old_env = os.environ.get("COZE_WORKSPACE_PATH")
        os.environ["COZE_WORKSPACE_PATH"] = str(tmp_path)
        from core.settings import reload_settings
        reload_settings()
        alpha_id = "did:aid:property_test"
        salt_path = os.path.join(str(tmp_path), "assets", ".salt_" + alpha_id.replace(":", "_"))
        if os.path.exists(salt_path):
            os.remove(salt_path)
        mgr = DualChainManager(alpha_id)
        yield mgr
        if old_env:
            os.environ["COZE_WORKSPACE_PATH"] = old_env
        else:
            os.environ.pop("COZE_WORKSPACE_PATH", None)
        reload_settings()

    @given(
        content=text(min_size=1, max_size=200),
        sensitivity=integers(min_value=0, max_value=100),
    )
    @settings(max_examples=30, deadline=None)
    def test_save_and_retrieve(self, manager, content, sensitivity):
        """任意内容 + 敏感度都能保存并取回原文"""
        result = manager.save(content, sensitivity=sensitivity)
        assert result["success"] is True
        record = manager.get(result["memory_id"])
        assert record is not None
        assert record["content"] == content

    @given(sensitivity=integers(min_value=0, max_value=100))
    @settings(max_examples=30, deadline=None)
    def test_chain_assignment_by_sensitivity(self, manager, sensitivity):
        """链分配严格按敏感度阈值"""
        result = manager.save("test content", sensitivity=sensitivity)
        if sensitivity >= PRIVACY_THRESHOLD:
            assert result["chain"] == "private"
            assert result["encrypted"] is True
        else:
            assert result["chain"] == "knowledge"
            assert result["encrypted"] is False

    @given(
        contents=lists(
            text(min_size=1, max_size=50),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=20, deadline=None)
    def test_stats_count_matches(self, manager, contents):
        """stats 计数与实际保存数量一致"""
        manager.clear_chain("private")
        manager.clear_chain("knowledge")
        for c in contents:
            manager.save(c, sensitivity=80)
        stats = manager.stats()
        assert stats.private_count == len(contents)
