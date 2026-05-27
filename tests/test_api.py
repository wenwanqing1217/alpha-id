"""
Alpha-ID API 集成测试

验证 FastAPI 路由层与核心模块的完整集成链路。
使用 temp JSON 数据库隔离测试数据，不依赖 PostgreSQL。

注意：需要 pydantic/fastapi 环境（Python 3.12+ 推荐，Python 3.14
需安装 Visual C++ Redistributable）。环境不支持时测试自动跳过。
"""
import json

import pytest

# 必须在导入 app 前设置路径
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 修复：pydantic_core 依赖 api-ms-win-crt-*.dll，系统缺失时手动添加搜索路径
_crt_search_path = r"D:\QQNT"
if os.path.isdir(_crt_search_path):
    os.add_dll_directory(_crt_search_path)

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


# ── 工厂：从路由模块内部替换管理器 ──


def _reset_identity_manager(db_path: str):
    """替换 identity 模块的全局管理器"""
    from core.user_identity import UserIdentityManager
    import api.identity as mod
    mod._manager = UserIdentityManager(db_path=db_path)


def _reset_social_manager(db_path: str):
    """替换 social 模块的全局管理器"""
    from core.alpha_social import AlphaSocialManager
    import api.social as mod
    mod._manager = AlphaSocialManager(db_path=db_path)


def _reset_risk_engine():
    """替换 risk 模块的全局引擎"""
    from core.risk_engine import RiskAssessmentEngine
    import api.risk as mod
    mod._engine = RiskAssessmentEngine()


# ── 临时 JSON 数据库 fixture ──


@pytest.fixture
def identity_db(tmp_path):
    db = tmp_path / "test_users.json"
    db.write_text(
        json.dumps({"users": {}, "counter": 0, "founder_registered": False}, indent=2),
        encoding="utf-8",
    )
    _reset_identity_manager(str(db))
    return str(db)


@pytest.fixture
def social_db(tmp_path):
    db = tmp_path / "test_social.json"
    db.write_text(
        json.dumps({"friends": {}, "friend_requests": {}, "messages": {}}, indent=2),
        encoding="utf-8",
    )
    _reset_social_manager(str(db))
    return str(db)


@pytest.fixture(autouse=True)
def _reset_all(identity_db, social_db):
    """每个测试前重置所有管理器"""
    _reset_risk_engine()
    yield


@pytest.fixture
def client():
    from src.main import app
    return TestClient(app)


# ── 注册辅助函数 ──


def register_user(client, device_fp: str, **kw) -> dict:
    resp = client.post("/api/v1/identity/register", json={
        "device_fingerprint": device_fp,
        **kw,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def login_user(client, alpha_id: str, device_fp: str) -> dict:
    """注册 + 登录，返回令牌信息"""
    resp = client.post("/api/v1/identity/login", json={
        "alpha_id": alpha_id,
        "device_fingerprint": device_fp,
    })
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
        resp = client.post("/api/v1/identity/login", json={
            "alpha_id": user["alpha_id"],
            "device_fingerprint": "fp-login-test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_user_not_found(self, client):
        resp = client.post("/api/v1/identity/login", json={
            "alpha_id": "AID-NOONE",
            "device_fingerprint": "fp-none",
        })
        assert resp.status_code == 404

    def test_login_no_devices(self, client, identity_db):
        """注册无设备用户后登录应失败（无权）"""
        from core.user_identity import UserIdentityManager
        mgr = UserIdentityManager()
        # 直接创建无设备的用户
        resp = client.post("/api/v1/identity/register", json={
            "device_fingerprint": "fp-nod",
        })
        alpha_id = resp.json()["alpha_id"]
        # 把设备列表清空
        import api.identity as mod
        mod._manager._data["users"][alpha_id]["devices"] = []
        mod._manager._save()
        resp2 = client.post("/api/v1/identity/login", json={
            "alpha_id": alpha_id,
            "device_fingerprint": "fp-nod",
        })
        assert resp2.status_code == 403

    def test_refresh_token(self, client, identity_db):
        user_data = register_and_login(client, "fp-refresh")
        resp = client.post("/api/v1/identity/refresh", json={
            "refresh_token": user_data["refresh_token"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["access_token"] != user_data["access_token"]

    def test_refresh_invalid_token(self, client):
        resp = client.post("/api/v1/identity/refresh", json={
            "refresh_token": "invalid-token",
        })
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
        resp = client.post("/api/v1/identity/refresh", json={
            "refresh_token": user_data["access_token"],
        })
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
        assert data["alpha_id"].startswith("AID-")

    def test_register_founder(self, client):
        data = register_user(client, "fp-founder", is_founder=True)
        assert data["success"] is True
        assert data["founder"] is True

    def test_register_duplicate(self, client):
        """同一设备重复注册应失败"""
        fp = "fp-duplicate"
        first = register_user(client, fp)
        assert first["success"] is True
        resp = client.post("/api/v1/identity/register", json={
            "device_fingerprint": fp,
        })
        assert resp.status_code == 400
        assert "已注册" in resp.json()["detail"]

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
        """每个测试前注册两个用户（依赖 identity 也在运行）"""
        # identity_db fixture 也在此生效（通过 autouse）
        self.alice = register_user(client, "fp-alice-soc")
        self.bob = register_user(client, "fp-bob-soc")

    def test_send_friend_request(self, client):
        resp = client.post("/api/v1/social/friend-request", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
            "message": "hello bob",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "request_id" in data

    def test_send_friend_request_missing(self, client):
        resp = client.post("/api/v1/social/friend-request", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": "AID-NOONE",
            "message": "",
        })
        assert resp.status_code == 400

    def test_accept_friend_request(self, client):
        # 发送请求
        req_resp = client.post("/api/v1/social/friend-request", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
        })
        request_id = req_resp.json()["request_id"]

        # 接受
        resp = client.put(f"/api/v1/social/friend-request/{request_id}", json={
            "response": "accept",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert self.alice["alpha_id"] in data["friends"]

    def test_reject_friend_request(self, client):
        req_resp = client.post("/api/v1/social/friend-request", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
        })
        request_id = req_resp.json()["request_id"]

        resp = client.put(f"/api/v1/social/friend-request/{request_id}", json={
            "response": "reject",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_get_friends(self, client):
        # 先成为好友
        req_resp = client.post("/api/v1/social/friend-request", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
        })
        rid = req_resp.json()["request_id"]
        client.put(f"/api/v1/social/friend-request/{rid}", json={"response": "accept"})

        resp = client.get(f"/api/v1/social/{self.alice['alpha_id']}/friends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["friends"][0]["alpha_id"] == self.bob["alpha_id"]

    def test_get_pending_requests(self, client):
        client.post("/api/v1/social/friend-request", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
        })

        resp = client.get(f"/api/v1/social/{self.bob['alpha_id']}/requests")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1

    def test_send_message(self, client):
        # 先成好友
        req_resp = client.post("/api/v1/social/friend-request", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
        })
        rid = req_resp.json()["request_id"]
        client.put(f"/api/v1/social/friend-request/{rid}", json={"response": "accept"})

        resp = client.post("/api/v1/social/message", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
            "content": "你好 Bob！",
            "message_type": "text",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_send_message_not_friends(self, client):
        resp = client.post("/api/v1/social/message", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
            "content": "hi",
        })
        assert resp.status_code == 400

    def test_get_messages(self, client):
        # 成好友+发消息
        req_resp = client.post("/api/v1/social/friend-request", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
        })
        rid = req_resp.json()["request_id"]
        client.put(f"/api/v1/social/friend-request/{rid}", json={"response": "accept"})
        client.post("/api/v1/social/message", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
            "content": "hi bob",
        })

        resp = client.get(f"/api/v1/social/{self.bob['alpha_id']}/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["messages"][0]["content"] == "hi bob"

    def test_get_messages_unread(self, client):
        req_resp = client.post("/api/v1/social/friend-request", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
        })
        rid = req_resp.json()["request_id"]
        client.put(f"/api/v1/social/friend-request/{rid}", json={"response": "accept"})
        client.post("/api/v1/social/message", json={
            "from_alpha_id": self.alice["alpha_id"],
            "to_alpha_id": self.bob["alpha_id"],
            "content": "unread test",
        })

        resp = client.get(f"/api/v1/social/{self.bob['alpha_id']}/messages?unread_only=true")
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

    def test_evaluate_full(self, client):
        resp = client.post("/api/v1/risk/evaluate", json={
            "device_current": {
                "hardware_id": "hw-001",
                "ip_address": "192.168.1.1",
                "location": "北京",
                "browser_info": "Chrome 120",
                "first_access_time": "2024-01-01T00:00:00Z",
            },
            "behavior_current": {
                "typing_speed": 85.5,
                "mouse_movement": "smooth",
                "session_time": 300.0,
                "input_pattern": "keyboard",
                "language": "zh-CN",
            },
            "voice_data": {
                "voice_match": 0.95,
                "habit_match": 0.88,
                "noise_level": 0.02,
                "audio_quality": 0.99,
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_score"] < 50  # 数据正常，风险较低
        assert data["total_assessments"] >= 1
