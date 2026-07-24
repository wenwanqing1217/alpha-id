"""JWT 认证模块纯单元测试（零外部依赖）"""

import time
import json
import pytest
from auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
    SecretKey,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    _b64url_encode,
    _b64url_decode,
    _hmac_sign,
    _encode,
)


# ── 基础工具测试 ──


class TestBase64Url:
    def test_roundtrip(self):
        data = b"hello world"
        encoded = _b64url_encode(data)
        decoded = _b64url_decode(encoded)
        assert decoded == data

    def test_padding_variations(self):
        """JWT 风格的无填充 base64url"""
        for s in (b"a", b"ab", b"abc", b"abcd", b"a" * 100):
            assert _b64url_decode(_b64url_encode(s)) == s

    def test_special_chars(self):
        data = b"\x00\x01\xff\xfe"
        encoded = _b64url_encode(data)
        decoded = _b64url_decode(encoded)
        assert decoded == data


class TestHmacSign:
    def test_deterministic(self):
        key = b"test-key-32-bytes-long!!!!!!!!"
        payload = "header.payload"
        sig1 = _hmac_sign(payload, key)
        sig2 = _hmac_sign(payload, key)
        assert sig1 == sig2

    def test_different_keys_different_sigs(self):
        key_a = b"a" * 32
        key_b = b"b" * 32
        payload = "header.payload"
        assert _hmac_sign(payload, key_a) != _hmac_sign(payload, key_b)

    def test_different_payloads_different_sigs(self):
        key = b"test-key-32-bytes-long!!!!!!!!"
        assert _hmac_sign("a.b", key) != _hmac_sign("a.c", key)


# ── SecretKey 单例测试 ──


class TestSecretKey:
    def test_singleton(self):
        a = SecretKey()
        b = SecretKey()
        assert a is b

    def test_key_is_32_bytes(self):
        key = SecretKey()
        assert len(key.bytes) == 32

    def test_hex_format(self):
        key = SecretKey()
        assert len(key.hex) == 64
        assert all(c in "0123456789abcdef" for c in key.hex)


# ── 令牌创建与验证测试 ──


class TestTokenCreation:
    def test_access_token_format(self):
        token = create_access_token("alpha-001")
        parts = token.split(".")
        assert len(parts) == 3
        # header
        header = json.loads(_b64url_decode(parts[0]))
        assert header["alg"] == "HS256"
        assert header["typ"] == "JWT"

    def test_access_token_subject(self):
        token = create_access_token("alpha-001")
        payload = decode_token(token)
        assert payload["sub"] == "alpha-001"
        assert payload["type"] == "access"

    def test_refresh_token_type(self):
        token = create_refresh_token("alpha-001")
        payload = decode_token(token)
        assert payload["sub"] == "alpha-001"
        assert payload["type"] == "refresh"

    def test_access_token_expiry(self):
        token = create_access_token("alpha-001")
        payload = decode_token(token)
        expected_exp = payload["iat"] + ACCESS_TOKEN_EXPIRE_MINUTES * 60
        assert payload["exp"] == expected_exp

    def test_refresh_token_expiry(self):
        token = create_refresh_token("alpha-001")
        payload = decode_token(token)
        expected_exp = payload["iat"] + REFRESH_TOKEN_EXPIRE_DAYS * 86400
        assert payload["exp"] == expected_exp

    def test_extra_claims(self):
        token = create_access_token("alpha-001", extra_claims={"scope": "admin"})
        payload = decode_token(token)
        assert payload["scope"] == "admin"

    def test_different_users_different_tokens(self):
        t1 = create_access_token("alpha-001")
        t2 = create_access_token("alpha-002")
        assert t1 != t2

    def test_iat_is_recent(self):
        token = create_access_token("alpha-001")
        payload = decode_token(token)
        now = time.time()
        assert abs(payload["iat"] - int(now)) < 5  # 5 秒误差


class TestTokenVerification:
    def test_verify_access_ok(self):
        token = create_access_token("alpha-001")
        alpha_id = verify_token(token, "access")
        assert alpha_id == "alpha-001"

    def test_verify_refresh_ok(self):
        token = create_refresh_token("alpha-001")
        alpha_id = verify_token(token, "refresh")
        assert alpha_id == "alpha-001"

    def test_verify_wrong_type(self):
        token = create_access_token("alpha-001")
        import pytest

        with pytest.raises(ValueError, match="令牌类型不匹配"):
            verify_token(token, "refresh")

    def test_tampered_payload(self):
        token = create_access_token("alpha-001")
        parts = token.split(".")
        # 篡改 payload 中的 sub
        tampered_payload = _b64url_encode(
            json.dumps({"sub": "attacker", "type": "access", "exp": 9999999999, "iat": 0}).encode()
        )
        bad_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
        import pytest

        with pytest.raises(ValueError, match="签名验证失败"):
            decode_token(bad_token)

    def test_tampered_header(self):
        token = create_access_token("alpha-001")
        parts = token.split(".")
        bad_header = _b64url_encode(json.dumps({"alg": "none"}).encode())
        bad_token = f"{bad_header}.{parts[1]}.{parts[2]}"
        import pytest

        with pytest.raises(ValueError, match="签名验证失败"):
            decode_token(bad_token)

    def test_expired_token(self):
        """创建一个已经过期的令牌"""
        import json, time

        payload = {
            "sub": "alpha-001",
            "iat": 0,
            "exp": 1,  # 1970 年的 1 秒后，必然过期
            "type": "access",
        }
        expired_token = _encode(payload)
        import pytest

        with pytest.raises(ValueError, match="令牌已过期"):
            decode_token(expired_token)

    def test_malformed_token(self):
        import pytest

        with pytest.raises(ValueError, match="令牌格式无效"):
            decode_token("not-a-jwt")
        with pytest.raises(ValueError, match="令牌格式无效"):
            decode_token("a.b")
        with pytest.raises(ValueError, match="令牌格式无效"):
            decode_token("a.b.c.d")


class TestVerifyTokenEdgeCases:
    def test_empty_string(self):
        import pytest

        with pytest.raises(ValueError, match="令牌格式无效"):
            verify_token("")

    def test_invalid_base64(self):
        import pytest

        with pytest.raises(ValueError):
            verify_token("header.payload!!!.signature")

    def test_unknown_type(self):
        """type 字段既不是 access 也不是 refresh"""
        token = _encode(
            {
                "sub": "alpha-001",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "type": "magic",
            }
        )
        import pytest

        with pytest.raises(ValueError, match="未知的令牌类型"):
            decode_token(token)


# ── get_current_alpha_id 测试 ──


class TestGetCurrentAlphaId:
    def test_valid_bearer(self):
        token = create_access_token("alpha-001")
        from auth.jwt import get_current_alpha_id

        alpha_id = get_current_alpha_id(f"Bearer {token}")
        assert alpha_id == "alpha-001"

    def test_missing_header(self):
        from auth.jwt import get_current_alpha_id
        import pytest

        with pytest.raises(ValueError, match="缺少 Authorization header"):
            get_current_alpha_id(None)

    def test_invalid_scheme(self):
        from auth.jwt import get_current_alpha_id
        import pytest

        with pytest.raises(ValueError, match="Authorization 必须是 Bearer 令牌"):
            get_current_alpha_id("Token abc123")

    def test_invalid_token(self):
        from auth.jwt import get_current_alpha_id
        import pytest

        with pytest.raises(ValueError):
            get_current_alpha_id("Bearer invalid-token-here")


# ── auth_verify 端点集成测试（跨服务验证） ──


class TestAuthVerifyEndpoint:
    """测试 POST /api/v1/identity/auth/verify 端点"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """创建测试用户并获取令牌"""
        from alpha_id.container import Container
        from core.storage import JsonStorage
        import tempfile, os

        self.tmp_dir = tempfile.mkdtemp(prefix="aid_verify_test_")
        os.environ["COZE_WORKSPACE_PATH"] = self.tmp_dir
        os.makedirs(os.path.join(self.tmp_dir, "assets"), exist_ok=True)

        # 重置容器单例
        Container._instance = None
        self.container = Container.instance()

        # 注册测试用户
        self.container.identity.register_user(
            device_fingerprint="test-device-001",
            is_founder=True,
            founder_code="Alpha-1-zx",
        )
        # 获取令牌
        self.access_token = create_access_token("Alpha-1")
        self.refresh_token = create_refresh_token("Alpha-1")

    def test_verify_valid_access_token(self):
        from fastapi.testclient import TestClient
        from src.main import app

        client = TestClient(app)
        resp = client.post("/api/v1/identity/auth/verify", json={"token": self.access_token})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["alpha_id"] == "Alpha-1"
        assert data["token_type"] == "access"

    def test_verify_valid_refresh_token(self):
        from fastapi.testclient import TestClient
        from src.main import app

        client = TestClient(app)
        resp = client.post("/api/v1/identity/auth/verify", json={"token": self.refresh_token})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["alpha_id"] == "Alpha-1"
        assert data["token_type"] == "refresh"

    def test_verify_invalid_token(self):
        from fastapi.testclient import TestClient
        from src.main import app

        client = TestClient(app)
        resp = client.post("/api/v1/identity/auth/verify", json={"token": "invalid.token.here"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "message" in data

    def test_verify_expired_token(self):
        from fastapi.testclient import TestClient
        from src.main import app

        expired = _encode({
            "sub": "Alpha-1",
            "iat": 0,
            "exp": 1,
            "type": "access",
        })
        client = TestClient(app)
        resp = client.post("/api/v1/identity/auth/verify", json={"token": expired})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "过期" in data["message"]

    def test_verify_missing_token_field(self):
        from fastapi.testclient import TestClient
        from src.main import app

        client = TestClient(app)
        resp = client.post("/api/v1/identity/auth/verify", json={})
        assert resp.status_code == 422  # Pydantic validation error
