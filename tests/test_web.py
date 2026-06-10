"""测试 Web 演示模块"""

import pytest
from fastapi.testclient import TestClient

from alpha_id.web import app
from alpha_id.container import Container


@pytest.fixture
def client():
    """TestClient + 容器重置"""
    Container.instance().reset()
    return TestClient(app)


class TestWebLogin:
    """登录/注册 API 测试"""

    def test_login_with_device_fp(self, client):
        resp = client.post("/login", json={"device_fingerprint": "web-test-device-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["alpha_id"].startswith("Alpha-")
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
        r1 = client.post("/login", json={"device_fingerprint": "web-test-device-same"})
        aid = r1.json()["alpha_id"]

        r2 = client.post("/login", json={"device_fingerprint": "web-test-device-same"})
        assert r2.json()["alpha_id"] == aid


class TestWebChat:
    """聊天 API 测试"""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        """先登录再测试聊天"""
        resp = client.post("/login", json={"device_fingerprint": "web-test-chat-user"})
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
        """无 API key 时返回未配置提示"""
        import os

        # 保存并清空 API key，确保走 _call_llm 的 no-key 分支
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        old_key2 = os.environ.pop("COZE_WORKLOAD_IDENTITY_API_KEY", None)
        try:
            resp = client.post(
                "/chat",
                json={
                    "alpha_id": self.alpha_id,
                    "message": "你是谁",
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
    """身份信息 API 测试"""

    def test_get_identity(self, client):
        # 先登录
        r = client.post("/login", json={"device_fingerprint": "web-test-id-device"})
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
    """首页测试"""

    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "Alpha-ID" in resp.text


class TestWebBrainControl:
    """大脑状态控制 API 测试"""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        resp = client.post("/login", json={"device_fingerprint": "web-test-brain-user"})
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
        # 休眠
        resp = client.post("/brain/sleep", json={"alpha_id": self.alpha_id})
        assert resp.status_code == 200
        assert resp.json()["state"] == "sleep"

        # 验证状态
        resp = client.get(f"/brain/status?alpha_id={self.alpha_id}")
        assert resp.json()["state"] == "sleep"

        # 唤醒
        resp = client.post("/brain/awake", json={"alpha_id": self.alpha_id})
        assert resp.status_code == 200
        assert resp.json()["state"] == "awake"

    def test_brain_think(self, client):
        resp = client.post("/brain/think", json={"alpha_id": self.alpha_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
