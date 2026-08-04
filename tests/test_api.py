"""
Alpha-ID API 集成测试

验证 FastAPI 路由层与核心模块的完整集成链路。
使用 temp JSON 数据库隔离测试数据，不依赖 PostgreSQL。

注意：需要 pydantic/fastapi 环境（Python 3.12+ 推荐，Python 3.14
需安装 Visual C++ Redistributable）。环境不支持时测试自动跳过。
"""

import hashlib
import os

import pytest

# 修复：pydantic_core 依赖 api-ms-win-crt-*.dll，系统缺失时手动添加搜索路径
_crt_search_path = r"D:\QQNT"
if os.path.isdir(_crt_search_path):
    os.add_dll_directory(_crt_search_path)

# 在导入任何使用 JWT 的模块前设置测试密钥
os.environ.setdefault("AUTH_MASTER_KEY", "test-master-key-256bit-secret-for-unit-tests-only")

try:
    from fastapi.testclient import TestClient

    _HAVE_FASTAPI = True
except ImportError:
    TestClient = None  # type: ignore
    _HAVE_FASTAPI = False

pytestmark = pytest.mark.skipif(
    not _HAVE_FASTAPI,
    reason="缺少 FastAPI/pydantic 环境（需要 Python 3.12+ 及 Visual C++ Redistributable）",
)


@pytest.fixture(autouse=True)
def _reset_all(tmp_path):
    """每个测试前：重置容器 + 注入临时 SQLite 数据库"""
    # 确保创始人验证码哈希已设置（强制覆盖，避免被外部环境变量污染）
    os.environ["FOUNDER_CODE_HASH"] = hashlib.sha256(b"Alpha-1-zx").hexdigest()
    from core.settings import reload_settings
    reload_settings()

    from alpha_id.container import Container
    from core.storage_sqlite import SqliteStorage

    container = Container.instance()
    container.reset()
    container.storage = SqliteStorage(str(tmp_path / "test.db"))
    yield


@pytest.fixture
def identity_db(_reset_all):
    """兼容旧测试签名：返回临时数据库路径"""
    return _reset_all  # 实际状态由 _reset_all 管理


@pytest.fixture
def social_db(_reset_all):
    """兼容旧测试签名"""
    return _reset_all


@pytest.fixture
def client():
    from src.main import app

    return TestClient(app)


# ── 注册辅助函数 ──


def register_user(client, device_fp: str, **kw) -> dict:
    resp = client.post(
        "/api/v1/identity/register",
        json={
            "device_fingerprint": device_fp,
            **kw,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def login_user(client, alpha_id: str, device_fp: str) -> dict:
    """注册 + 登录，返回令牌信息"""
    resp = client.post(
        "/api/v1/identity/login",
        json={
            "alpha_id": alpha_id,
            "device_fingerprint": device_fp,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def register_and_login(client, device_fp: str, **kw) -> dict:
    """注册用户并登录，返回 alpha_id + token 信息"""
    user = register_user(client, device_fp, **kw)
    token_data = login_user(client, user["alpha_id"], device_fp)
    return {
        **user,
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
    }


# ════════════════════════════════════════════════════════════
# 认证 API 测试
# ════════════════════════════════════════════════════════════


class TestAuthAPI:
    """认证流程集成测试"""

    def test_login_success(self, client, identity_db):
        user = register_user(client, "fp-login-test")
        resp = client.post(
            "/api/v1/identity/login",
            json={
                "alpha_id": user["alpha_id"],
                "device_fingerprint": "fp-login-test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_user_not_found(self, client):
        resp = client.post(
            "/api/v1/identity/login",
            json={
                "alpha_id": "AID-NOONE",
                "device_fingerprint": "fp-none",
            },
        )
        assert resp.status_code == 404

    def test_login_no_devices(self, client, identity_db):
        """注册无设备用户后登录应失败（无权）"""
        from alpha_id.container import Container

        # 直接创建无设备的用户
        resp = client.post(
            "/api/v1/identity/register",
            json={
                "device_fingerprint": "fp-nod",
            },
        )
        alpha_id = resp.json()["alpha_id"]
        # 把设备列表清空
        container = Container.instance()
        users = container.storage.load("users")
        users[alpha_id]["devices"] = []
        container.storage.save("users", users)
        resp2 = client.post(
            "/api/v1/identity/login",
            json={
                "alpha_id": alpha_id,
                "device_fingerprint": "fp-nod",
            },
        )
        assert resp2.status_code == 403

    def test_refresh_token(self, client, identity_db):
        user_data = register_and_login(client, "fp-refresh")
        resp = client.post(
            "/api/v1/identity/refresh",
            json={
                "refresh_token": user_data["refresh_token"],
            },
        )
        assert resp.status_code in (200, 202)
        data = resp.json()
        assert "access_token" in data
        assert data["access_token"] is not None

    def test_refresh_invalid_token(self, client):
        resp = client.post(
            "/api/v1/identity/refresh",
            json={
                "refresh_token": "invalid-token",
            },
        )
        assert resp.status_code == 401

    def test_me_endpoint(self, client, identity_db):
        user_data = register_and_login(client, "fp-me")
        resp = client.get(
            "/api/v1/identity/me",
            headers={"Authorization": f"Bearer {user_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["alpha_id"] == user_data["alpha_id"]

    def test_me_unauthorized(self, client):
        resp = client.get("/api/v1/identity/me")
        assert resp.status_code == 401

    def test_protected_endpoint_with_bearer(self, client, identity_db):
        user_data = register_and_login(client, "fp-protected")
        # /devices 需要认证
        resp = client.post(
            f"/api/v1/identity/{user_data['alpha_id']}/devices",
            json={"new_device": "fp-new-device"},
            headers={"Authorization": f"Bearer {user_data['access_token']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_protected_endpoint_no_auth(self, client, identity_db):
        user_data = register_and_login(client, "fp-noauth")
        # 不带 token 访问受保护端点
        resp = client.post(
            f"/api/v1/identity/{user_data['alpha_id']}/devices",
            json={"new_device": "fp-new-device"},
        )
        assert resp.status_code == 401

    def test_protected_endpoint_bad_token(self, client, identity_db):
        user_data = register_and_login(client, "fp-badtoken")
        resp = client.post(
            f"/api/v1/identity/{user_data['alpha_id']}/devices",
            json={"new_device": "fp-new-device"},
            headers={"Authorization": "Bearer badtoken"},
        )
        assert resp.status_code == 401

    def test_refresh_access_denied(self, client, identity_db):
        """证明访问令牌不能用于 refresh 端点"""
        user_data = register_and_login(client, "fp-refdeny")
        resp = client.post(
            "/api/v1/identity/refresh",
            json={
                "refresh_token": user_data["access_token"],
            },
        )
        assert resp.status_code == 401
        assert "令牌类型不匹配" in resp.json()["detail"]


# ════════════════════════════════════════════════════════════
# 身份 API 测试
# ════════════════════════════════════════════════════════════


class TestIdentityAPI:
    """用户身份 API 集成测试"""

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_register(self, client):
        data = register_user(client, "fp-macbook-pro")
        assert data["success"] is True
        assert data["alpha_id"].startswith("Alpha-")

    def test_register_founder(self, client):
        data = register_user(client, "fp-founder", is_founder=True, founder_code="Alpha-1-zx")
        assert data["success"] is True
        assert data["is_founder"] is True

    def test_register_duplicate(self, client):
        """同一设备重复注册应返回已有账号（幂等设计）"""
        fp = "fp-duplicate"
        first = register_user(client, fp)
        assert first["success"] is True
        resp = client.post(
            "/api/v1/identity/register",
            json={
                "device_fingerprint": fp,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["already_registered"] is True
        assert "alpha_id" in data

    def test_get_profile(self, client):
        user_data = register_and_login(client, "fp-profile")
        resp = client.get(
            f"/api/v1/identity/{user_data['alpha_id']}",
            headers={"Authorization": f"Bearer {user_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["alpha_id"] == user_data["alpha_id"]

    def test_get_profile_not_found(self, client):
        user_data = register_and_login(client, "fp-profile-nf")
        resp = client.get(
            "/api/v1/identity/AID-NONEXIST",
            headers={"Authorization": f"Bearer {user_data['access_token']}"},
        )
        assert resp.status_code == 404

    def test_bind_device(self, client):
        user_data = register_and_login(client, "fp-device-original")
        resp = client.post(
            f"/api/v1/identity/{user_data['alpha_id']}/devices",
            json={"new_device": "fp-device-new"},
            headers={"Authorization": f"Bearer {user_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_bind_device_invalid_user(self, client):
        user_data = register_and_login(client, "fp-device-bad")
        resp = client.post(
            "/api/v1/identity/AID-BAD/devices",
            json={"new_device": "fp-whatever"},
            headers={"Authorization": f"Bearer {user_data['access_token']}"},
        )
        assert resp.status_code == 400

    def test_sync_device(self, client):
        user_data = register_and_login(client, "fp-sync-original")
        # 先绑定第二个设备
        client.post(
            f"/api/v1/identity/{user_data['alpha_id']}/devices",
            json={"new_device": "fp-sync-second"},
            headers={"Authorization": f"Bearer {user_data['access_token']}"},
        )
        resp = client.post(
            f"/api/v1/identity/{user_data['alpha_id']}/sync",
            json={
                "from_device": "fp-sync-original",
                "to_device": "fp-sync-second",
            },
            headers={"Authorization": f"Bearer {user_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_sync_device_invalid(self, client):
        user_data = register_and_login(client, "fp-sync-bad")
        resp = client.post(
            "/api/v1/identity/AID-BAD/sync",
            json={"from_device": "a", "to_device": "b"},
            headers={"Authorization": f"Bearer {user_data['access_token']}"},
        )
        assert resp.status_code == 400

    def test_record_session(self, client):
        user_data = register_and_login(client, "fp-session")
        resp = client.post(
            f"/api/v1/identity/{user_data['alpha_id']}/session",
            headers={"Authorization": f"Bearer {user_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_statistics(self, client):
        register_user(client, "fp-stat1")
        register_user(client, "fp-stat2")
        resp = client.get("/api/v1/identity/stats/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users"] >= 2


# ════════════════════════════════════════════════════════════
# 社交 API 测试
# ════════════════════════════════════════════════════════════


class TestSocialAPI:
    """社交网络 API 集成测试"""

    @pytest.fixture(autouse=True)
    def _setup_users(self, client, identity_db, social_db):
        """每个测试前注册两个用户并登录获取令牌"""
        self.alice = register_user(client, "fp-alice-soc")
        self.alice["token"] = login_user(client, self.alice["alpha_id"], "fp-alice-soc")["access_token"]

        self.bob = register_user(client, "fp-bob-soc")
        self.bob["token"] = login_user(client, self.bob["alpha_id"], "fp-bob-soc")["access_token"]

    def _auth_headers(self, user):
        return {"Authorization": f"Bearer {user['token']}"}

    def test_send_friend_request(self, client):
        resp = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
                "message": "hello bob",
            },
            headers=self._auth_headers(self.alice),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "request_id" in data

    def test_send_friend_request_missing(self, client):
        resp = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": "AID-NOONE",
                "message": "",
            },
            headers=self._auth_headers(self.alice),
        )
        # social manager 不验证用户是否存在，只关心请求是否成功发送
        assert resp.status_code == 200

    def test_accept_friend_request(self, client):
        # 发送请求
        req_resp = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
            },
            headers=self._auth_headers(self.alice),
        )
        request_id = req_resp.json()["request_id"]

        # 接受
        resp = client.put(
            f"/api/v1/social/friend-request/{request_id}",
            json={
                "response": "accept",
            },
            headers=self._auth_headers(self.bob),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["friend_added"] is True

    def test_reject_friend_request(self, client):
        req_resp = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
            },
            headers=self._auth_headers(self.alice),
        )
        request_id = req_resp.json()["request_id"]

        resp = client.put(
            f"/api/v1/social/friend-request/{request_id}",
            json={
                "response": "reject",
            },
            headers=self._auth_headers(self.bob),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_get_friends(self, client):
        # 先成为好友
        req_resp = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
            },
            headers=self._auth_headers(self.alice),
        )
        rid = req_resp.json()["request_id"]
        client.put(f"/api/v1/social/friend-request/{rid}", json={"response": "accept"}, headers=self._auth_headers(self.bob))

        resp = client.get(f"/api/v1/social/{self.alice['alpha_id']}/friends", headers=self._auth_headers(self.alice))
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["friends"][0] == self.bob["alpha_id"]

    def test_get_pending_requests(self, client):
        client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
            },
            headers=self._auth_headers(self.alice),
        )

        resp = client.get(f"/api/v1/social/{self.bob['alpha_id']}/requests", headers=self._auth_headers(self.bob))
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1

    def test_send_message(self, client):
        # 先成好友
        req_resp = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
            },
            headers=self._auth_headers(self.alice),
        )
        rid = req_resp.json()["request_id"]
        client.put(f"/api/v1/social/friend-request/{rid}", json={"response": "accept"}, headers=self._auth_headers(self.bob))

        resp = client.post(
            "/api/v1/social/message",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
                "content": "你好 Bob！",
                "message_type": "text",
            },
            headers=self._auth_headers(self.alice),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_send_message_not_friends(self, client):
        resp = client.post(
            "/api/v1/social/message",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
                "content": "hi",
            },
            headers=self._auth_headers(self.alice),
        )
        assert resp.status_code == 400

    def test_get_messages(self, client):
        # 成好友+发消息
        req_resp = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
            },
            headers=self._auth_headers(self.alice),
        )
        rid = req_resp.json()["request_id"]
        client.put(f"/api/v1/social/friend-request/{rid}", json={"response": "accept"}, headers=self._auth_headers(self.bob))
        client.post(
            "/api/v1/social/message",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
                "content": "hi bob",
            },
            headers=self._auth_headers(self.alice),
        )

        resp = client.get(f"/api/v1/social/{self.bob['alpha_id']}/messages", headers=self._auth_headers(self.bob))
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["messages"][0]["content"] == "hi bob"

    def test_get_messages_unread(self, client):
        req_resp = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
            },
            headers=self._auth_headers(self.alice),
        )
        rid = req_resp.json()["request_id"]
        client.put(f"/api/v1/social/friend-request/{rid}", json={"response": "accept"}, headers=self._auth_headers(self.bob))
        client.post(
            "/api/v1/social/message",
            json={
                "from_alpha_id": self.alice["alpha_id"],
                "to_alpha_id": self.bob["alpha_id"],
                "content": "unread test",
            },
            headers=self._auth_headers(self.alice),
        )

        resp = client.get(f"/api/v1/social/{self.bob['alpha_id']}/messages?unread_only=true", headers=self._auth_headers(self.bob))
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1


# ════════════════════════════════════════════════════════════
# 风控 API 测试
# ════════════════════════════════════════════════════════════


class TestRiskAPI:
    """风控引擎 API 集成测试"""

    def test_evaluate_empty(self, client):
        resp = client.post("/api/v1/risk/evaluate", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_score" in data
        assert "risk_level" in data
        assert "action_required" in data

    def test_voice_verify_low_risk(self, client):
        """高声纹匹配 → 低风险"""
        resp = client.post(
            "/api/v1/risk/voice-verify",
            json={
                "voice_match": 0.98,
                "habit_match": 0.95,
                "user_id": "test-user-001",
                "noise_level": 0.01,
                "audio_quality": 0.99,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["voice_score"] > 80
        assert data["risk_score"] < 20
        assert data["risk_level"] in ("安全区", "警戒区")

    def test_voice_verify_high_risk(self, client):
        """低声纹匹配 → 高风险"""
        resp = client.post(
            "/api/v1/risk/voice-verify",
            json={
                "voice_match": 0.15,
                "habit_match": 0.20,
                "user_id": "test-user-001",
                "noise_level": 0.85,
                "audio_quality": 0.30,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["voice_score"] < 40
        assert data["risk_score"] > 60
        assert data["risk_level"] in ("警戒区", "危险区")
        assert data["action_required"]

    def test_voice_verify_response_shape(self, client):
        """验证响应字段完整性"""
        resp = client.post(
            "/api/v1/risk/voice-verify",
            json={
                "voice_match": 0.50,
                "habit_match": 0.50,
                "user_id": "test-user-001",
                "noise_level": 0.50,
                "audio_quality": 0.50,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "voice_score",
            "risk_score",
            "risk_level",
            "action_required",
            "recommended_verification",
        }

    def test_evaluate_full(self, client):
        resp = client.post(
            "/api/v1/risk/evaluate",
            json={
                "device_current": {
                    "hardware_id": "hw-001",
                    "ip_address": "192.168.1.1",
                    "location": "北京",
                    "browser_info": "Chrome 120",
                    "screen_resolution": "1920x1080",
                    "first_access_time": "2024-01-01T00:00:00Z",
                },
                "behavior_current": {
                    "typing_speed": 85.5,
                    "session_time": "05:00",
                    "common_words": [],
                    "error_rate": 0.0,
                    "word_count": 0,
                    "emoji_count": 0,
                },
                "voice_data": {
                    "voice_match": 0.95,
                    "habit_match": 0.88,
                    "noise_level": 0.02,
                    "audio_quality": 0.99,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_score"] < 50  # 数据正常，风险较低
        assert data["device_score"] >= 0
        assert data["behavior_score"] >= 0
        assert data["voice_score"] >= 0
