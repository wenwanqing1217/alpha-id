"""JWT 认证模块单元测试 — 基于 PyJWT"""

import time
import json
import base64
import pytest

from auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
    ALGORITHM,
)
from core.settings import settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (4 - len(data) % 4) if len(data) % 4 else ""
    return base64.urlsafe_b64decode(data + padding)


def _encode(payload: dict) -> str:
    import jwt as pyjwt
    from auth.jwt import _get_signing_key
    return pyjwt.encode(payload, _get_signing_key(), algorithm=ALGORITHM)


# ── 令牌创建与验证测试 ──


class TestTokenCreation:
    def test_access_token_format(self):
        token = create_access_token("alpha-001")
        parts = token.split(".")
        assert len(parts) == 3
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
        expected_exp = payload["iat"] + settings.jwt_access_expire_minutes * 60
        assert payload["exp"] == expected_exp

    def test_refresh_token_expiry(self):
        token = create_refresh_token("alpha-001")
        payload = decode_token(token)
        expected_exp = payload["iat"] + settings.jwt_refresh_expire_days * 86400
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
        assert abs(payload["iat"] - int(now)) < 5


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
        with pytest.raises(ValueError, match="令牌类型不匹配"):
            verify_token(token, "refresh")

    def test_tampered_payload(self):
        token = create_access_token("alpha-001")
        parts = token.split(".")
        tampered_payload = _b64url_encode(
            json.dumps({"sub": "attacker", "type": "access", "exp": 9999999999, "iat": 0}).encode()
        )
        bad_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
        with pytest.raises(ValueError):
            decode_token(bad_token)

    def test_tampered_header(self):
        token = create_access_token("alpha-001")
        parts = token.split(".")
        bad_header = _b64url_encode(json.dumps({"alg": "none"}).encode())
        bad_token = f"{bad_header}.{parts[1]}.{parts[2]}"
        with pytest.raises(ValueError):
            decode_token(bad_token)

    def test_expired_token(self):
        expired_payload = {
            "sub": "alpha-001",
            "iat": 0,
            "exp": 1,
            "type": "access",
        }
        expired_token = _encode(expired_payload)
        with pytest.raises(ValueError, match="令牌已过期"):
            decode_token(expired_token)

    def test_malformed_token(self):
        with pytest.raises(ValueError):
            decode_token("not-a-jwt")
        with pytest.raises(ValueError):
            decode_token("a.b")
        with pytest.raises(ValueError):
            decode_token("a.b.c.d")


class TestVerifyTokenEdgeCases:
    def test_empty_string(self):
        with pytest.raises(ValueError):
            verify_token("")

    def test_invalid_base64(self):
        with pytest.raises(ValueError):
            verify_token("header.payload!!!.signature")

    def test_unknown_type(self):
        token = _encode(
            {
                "sub": "alpha-001",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "type": "magic",
            }
        )
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

        with pytest.raises(ValueError, match="缺少 Authorization header"):
            get_current_alpha_id(None)

    def test_invalid_scheme(self):
        from auth.jwt import get_current_alpha_id

        with pytest.raises(ValueError, match="Authorization 必须是 Bearer 令牌"):
            get_current_alpha_id("Token abc123")

    def test_invalid_token(self):
        from auth.jwt import get_current_alpha_id

        with pytest.raises(ValueError):
            get_current_alpha_id("Bearer invalid-token-here")


# ── auth_verify 端点集成测试 ──


class TestAuthVerifyEndpoint:
    """测试 POST /api/v1/identity/auth/verify 端点"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from alpha_id.container import Container
        import tempfile, os

        self.tmp_dir = tempfile.mkdtemp(prefix="aid_verify_test_")
        os.environ["COZE_WORKSPACE_PATH"] = self.tmp_dir
        os.makedirs(os.path.join(self.tmp_dir, "assets"), exist_ok=True)

        # 保存旧单例，测试结束后恢复，避免破坏后续测试
        self._old_instance = Container._instance
        Container._instance = None
        self.container = Container.instance()

        self.container.identity.register_user(
            device_fingerprint="test-device-001",
            is_founder=True,
            founder_code="Alpha-1-zx",
        )
        self.access_token = create_access_token("Alpha-1")
        self.refresh_token = create_refresh_token("Alpha-1")
        yield
        # 恢复旧单例（close 新建的单例，回滚到测试前状态）
        if self.container is not None:
            try:
                self.container.close()
            except Exception:
                pass
        Container._instance = self._old_instance

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
        assert resp.status_code == 422
