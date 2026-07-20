"""Test Web display module"""

import sys, os, uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from fastapi.testclient import TestClient

from alpha_id.container import Container
from alpha_id.web import app
from src.main import app as api_app


def _unique_fp() -> str:
    return f"web-test-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def client():
    """TestClient + device setup + register test user"""
    Container.instance().reset()

    # Register test user (via API)
    api_client = TestClient(api_app)
    fp = _unique_fp()
    resp = api_client.post("/api/v1/identity/register", json={"device_fingerprint": fp})
    assert resp.status_code == 200, f"Registration failed: {resp.text}"
    alpha_id = resp.json()["alpha_id"]

    web_client = TestClient(app)
    web_client._alpha_id = alpha_id
    web_client._fp = fp
    return web_client


class TestWebLogin:
    """Login/register API tests"""

    def test_login_with_device_fp(self, client):
        alpha_id = client._alpha_id
        resp = client.post(
            "/login",
            json={"device_fingerprint": "web-test-device-1", "alpha_id": alpha_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["alpha_id"] == alpha_id
        assert data["action"] in ("login", "register")

    def test_login_empty_device_fp(self, client):
        resp = client.post("/login", json={"device_fingerprint": ""})
        assert resp.status_code == 400
        assert "不能为空" in resp.json()["error"]

    def test_login_nonexistent_alpha_id(self, client):
        resp = client.post(
            "/login",
            json={
                "device_fingerprint": "web-test-device-2",
                "alpha_id": "Alpha-Nonexistent",
            },
        )
        assert resp.status_code == 404

    def test_login_twice_returns_same_alpha_id(self, client):
        alpha_id = client._alpha_id
        r1 = client.post(
            "/login",
            json={"device_fingerprint": "web-test-device-same", "alpha_id": alpha_id},
        )
        aid = r1.json()["alpha_id"]

        r2 = client.post(
            "/login",
            json={"device_fingerprint": "web-test-device-same", "alpha_id": alpha_id},
        )
        assert r2.json()["alpha_id"] == aid


class TestWebChat:
    """Chat API tests"""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        """Login before testing chat"""
        alpha_id = client._alpha_id
        resp = client.post(
            "/login",
            json={"device_fingerprint": "web-test-chat-user", "alpha_id": alpha_id},
        )
        data = resp.json()
        self.alpha_id = data["alpha_id"]
        assert data["success"]

    def test_chat_requires_alpha_id(self, client):
        resp = client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 400

    def test_chat_requires_message(self, client):
        resp = client.post("/chat", json={"alpha_id": self.alpha_id, "message": ""})
        assert resp.status_code == 400

    def test_chat_unauthenticated(self, client):
        resp = client.post("/chat", json={"alpha_id": "Alpha-Nobody", "message": "hi"})
        assert resp.status_code == 401

    def test_chat_basic(self, client):
        """Without API key returns unconfigured prompt"""
        import os

        # Save and clear API keys to ensure _call_llm hits the no-key branch
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        old_key2 = os.environ.pop("COZE_WORKLOAD_IDENTITY_API_KEY", None)
        try:
            resp = client.post(
                "/chat",
                json={
                    "alpha_id": self.alpha_id,
                    "message": "Hello",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "reply" in data
            assert data["agent"]["alpha_id"] == self.alpha_id
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key
            if old_key2:
                os.environ["COZE_WORKLOAD_IDENTITY_API_KEY"] = old_key2


class TestWebIdentity:
    """Identity info API tests"""

    def test_get_identity(self, client):
        # Login first
        alpha_id = client._alpha_id
        r = client.post(
            "/login",
            json={"device_fingerprint": "web-test-id-device", "alpha_id": alpha_id},
        )
        aid = r.json()["alpha_id"]

        resp = client.get("/identity", headers={"X-Alpha-ID": aid})
        assert resp.status_code == 200
        data = resp.json()
        assert data["alpha_id"] == aid
        assert "profile" in data
        assert "friends" in data

    def test_get_identity_no_header(self, client):
        resp = client.get("/identity")
        assert resp.status_code == 400

    def test_get_identity_nonexistent(self, client):
        resp = client.get("/identity", headers={"X-Alpha-ID": "Alpha-ZZZ"})
        assert resp.status_code == 404


class TestWebIndex:
    """Homepage tests"""

    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "Alpha-ID" in resp.text


class TestWebBrainControl:
    """Brain state control API tests"""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        alpha_id = client._alpha_id
        resp = client.post(
            "/login",
            json={"device_fingerprint": "web-test-brain-user", "alpha_id": alpha_id},
        )
        data = resp.json()
        self.alpha_id = data["alpha_id"]
        assert data["success"]

    def test_brain_status(self, client):
        resp = client.get(f"/brain/status?alpha_id={self.alpha_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        assert data["alpha_id"] == self.alpha_id
        assert data["state"] == "awake"

    def test_brain_status_missing_id(self, client):
        resp = client.get("/brain/status")
        assert resp.status_code == 400
        assert "不能为空" in resp.json()["error"]

    def test_brain_status_nonexistent(self, client):
        resp = client.get("/brain/status?alpha_id=Alpha-Nobody")
        assert resp.status_code == 404

    def test_brain_sleep_and_awake(self, client):
        # Sleep
        resp = client.post("/brain/sleep", json={"alpha_id": self.alpha_id})
        assert resp.status_code == 200
        assert resp.json()["state"] == "sleep"

        # Verify state
        resp = client.get(f"/brain/status?alpha_id={self.alpha_id}")
        assert resp.json()["state"] == "sleep"

        # Wake up
        resp = client.post("/brain/awake", json={"alpha_id": self.alpha_id})
        assert resp.status_code == 200
        assert resp.json()["state"] == "awake"

    def test_brain_think(self, client):
        resp = client.post("/brain/think", json={"alpha_id": self.alpha_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]


class TestWebProfileApi:
    def test_api_profile_returns_empty_profile(self, client):
        resp = client.get("/api/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert "collected_sources" in data
        assert "provenance" in data
        assert data["collected_sources"] == []
        assert data["provenance"] == {}

    def test_api_profile_reflects_collected_sources(self, client):
        from alpha_id.profile_schema import AlphaIDProfile, save_profile

        profile = AlphaIDProfile(did="did:aid:test", created_at="2026-01-01T00:00:00Z")
        profile.extra["x_collected_sources"] = ["git", "browser"]
        profile.extra["x_provenance"] = {"tone": {"source": "cursor", "confidence": 0.8}}
        save_profile(profile)
        resp = client.get("/api/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["profile"]["did"] == "did:aid:test"
        assert data["collected_sources"] == ["git", "browser"]
        assert data["provenance"]["tone"]["source"] == "cursor"
