"""E2E 全链路测试 — FastAPI TestClient → API 路由 → core 模块

覆盖三大 API 模块的全流程：
  1. 身份（register → login → /me → profile → refresh → device/session）
  2. 社交（双用户注册 → 好友请求 → 审批 → 消息 → 边界）
  3. 风控（设备评分/行为评分/声纹评分全量评估 + 独立声纹验证）

Auth / 401 / 404 边界也在覆盖范围内。

注意：每次测试会重置 Container + 注入临时 SQLite 数据库，完全隔离。
"""

import os
import json
import sys

import pytest
from fastapi.testclient import TestClient

# 在导入 main/app 前设置 JWT 测试密钥
os.environ.setdefault("AUTH_MASTER_KEY", "test-master-key-256bit-secret-for-unit-tests-only")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.main import app
from auth.jwt import create_access_token

_fixture_counter = [0]  # mutable counter for unique device fingerprints


# ── Fixtures ──


@pytest.fixture(autouse=True)
def reset_all(tmp_path):
    """每次测试前：重置容器 + 注入临时 SQLite 数据库"""
    from alpha_id.container import Container
    from core.storage_sqlite import SqliteStorage

    container = Container.instance()
    container.reset()
    container.storage = SqliteStorage(str(tmp_path / "e2e_test.db"))
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def registered_user(client: TestClient):
    """注册一个测试用户，每次调用用唯一设备指纹"""
    _fixture_counter[0] += 1
    fp = f"e2e-device-{_fixture_counter[0]:03d}"
    resp = client.post(
        "/api/v1/identity/register",
        json={
            "device_fingerprint": fp,
        },
    )
    assert resp.status_code == 200
    alpha_id = resp.json()["alpha_id"]

    login_resp = client.post(
        "/api/v1/identity/login",
        json={
            "alpha_id": alpha_id,
            "device_fingerprint": fp,
        },
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return alpha_id, token


# ==================================================================
# 1. 身份模块 E2E
# ==================================================================


class TestIdentityE2E:
    """用户身份全流程"""

    def test_register_and_login(self, client: TestClient):
        """注册 → 登录 → 获取令牌"""
        resp = client.post(
            "/api/v1/identity/register",
            json={
                "device_fingerprint": "dev-fp-abc",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["alpha_id"].startswith("Alpha-")
        alpha_id = data["alpha_id"]

        login_resp = client.post(
            "/api/v1/identity/login",
            json={
                "alpha_id": alpha_id,
                "device_fingerprint": "dev-fp-abc",
            },
        )
        assert login_resp.status_code == 200
        tokens = login_resp.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"

    def test_login_nonexistent_user_returns_404(self, client: TestClient):
        resp = client.post(
            "/api/v1/identity/login",
            json={
                "alpha_id": "Alpha-Nobody",
                "device_fingerprint": "whatever",
            },
        )
        assert resp.status_code == 404

    def test_login_with_empty_device_fp_registered(self, client: TestClient):
        """空 device_fingerprint 注册 → 仍会被存入 devices=[""] → login 成功"""
        resp = client.post(
            "/api/v1/identity/register",
            json={
                "device_fingerprint": "",
            },
        )
        assert resp.status_code == 200
        alpha_id = resp.json()["alpha_id"]

        login_resp = client.post(
            "/api/v1/identity/login",
            json={
                "alpha_id": alpha_id,
                "device_fingerprint": "",
            },
        )
        # devices=[ "" ]，非空列表 → login 成功
        assert login_resp.status_code == 200

    def test_get_me_with_valid_token(self, client: TestClient, registered_user):
        alpha_id, token = registered_user
        resp = client.get(
            "/api/v1/identity/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        profile = resp.json()
        assert profile["alpha_id"] == alpha_id

    def test_get_me_without_token_returns_401(self, client: TestClient):
        resp = client.get("/api/v1/identity/me")
        assert resp.status_code == 401

    def test_get_me_with_bad_token_returns_401(self, client: TestClient):
        resp = client.get(
            "/api/v1/identity/me",
            headers={"Authorization": "Bearer this.is.not.a.valid.token"},
        )
        assert resp.status_code == 401

    def test_get_profile_requires_auth(self, client: TestClient, registered_user):
        alpha_id, token = registered_user
        # 有令牌
        resp = client.get(
            f"/api/v1/identity/{alpha_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["alpha_id"] == alpha_id

        # 无令牌
        resp2 = client.get(f"/api/v1/identity/{alpha_id}")
        assert resp2.status_code == 401

    def test_get_nonexistent_profile_returns_404(self, client: TestClient):
        token = create_access_token("Alpha-Tester")
        resp = client.get(
            "/api/v1/identity/Alpha-Nobody",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_refresh_token(self, client: TestClient):
        """注册 → 登录 → refresh → 新令牌可用"""
        fp = "refresh-device"
        client.post(
            "/api/v1/identity/register",
            json={
                "device_fingerprint": fp,
            },
        )
        login_resp = client.post(
            "/api/v1/identity/login",
            json={
                "alpha_id": "Alpha-001",
                "device_fingerprint": fp,
            },
        )
        assert login_resp.status_code == 200
        refresh_token = login_resp.json()["refresh_token"]

        refresh_resp = client.post(
            "/api/v1/identity/refresh",
            json={
                "refresh_token": refresh_token,
            },
        )
        assert refresh_resp.status_code == 200
        new_token = refresh_resp.json()["access_token"]

        # 新令牌可以访问受保护端点
        me = client.get(
            "/api/v1/identity/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert me.status_code == 200

    def test_bad_refresh_token_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/v1/identity/refresh",
            json={
                "refresh_token": "totally.fake.token",
            },
        )
        assert resp.status_code == 401

    def test_bind_device(self, client: TestClient, registered_user):
        alpha_id, token = registered_user
        resp = client.post(
            f"/api/v1/identity/{alpha_id}/devices",
            json={"new_device": "new-device-fp-999"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_record_session(self, client: TestClient, registered_user):
        alpha_id, token = registered_user
        resp = client.post(
            f"/api/v1/identity/{alpha_id}/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_get_statistics(self, client: TestClient):
        """统计端点公开可访问 — 空存储时返回零值"""
        resp = client.get("/api/v1/identity/stats/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users"] == 0


# ==================================================================
# 2. 社交模块 E2E
# ==================================================================


class TestSocialE2E:
    """好友关系全流程"""

    @pytest.fixture
    def two_users(self, client: TestClient):
        """注册两个用户，设备指纹唯一"""
        fp_a = "social-a"
        r1 = client.post(
            "/api/v1/identity/register",
            json={
                "device_fingerprint": fp_a,
            },
        )
        assert r1.status_code == 200
        a_id = r1.json()["alpha_id"]
        t1 = client.post(
            "/api/v1/identity/login",
            json={
                "alpha_id": a_id,
                "device_fingerprint": fp_a,
            },
        ).json()["access_token"]

        fp_b = "social-b"
        r2 = client.post(
            "/api/v1/identity/register",
            json={
                "device_fingerprint": fp_b,
            },
        )
        assert r2.status_code == 200
        b_id = r2.json()["alpha_id"]
        t2 = client.post(
            "/api/v1/identity/login",
            json={
                "alpha_id": b_id,
                "device_fingerprint": fp_b,
            },
        ).json()["access_token"]

        return (a_id, t1), (b_id, t2)

    def test_send_and_accept_friend_request(self, client: TestClient, two_users):
        (a_id, t1), (b_id, t2) = two_users

        # A 向 B 发送好友请求
        send = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": a_id,
                "to_alpha_id": b_id,
                "message": "你好，做个朋友吧",
            },
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert send.status_code == 200
        request_id = send.json()["request_id"]

        # B 查看 pending 请求
        pending = client.get(
            f"/api/v1/social/{b_id}/requests",
            headers={"Authorization": f"Bearer {t2}"},
        )
        assert pending.status_code == 200
        assert pending.json()["count"] == 1
        assert pending.json()["requests"][0]["from_alpha_id"] == a_id

        # B 接受请求
        accept = client.put(
            f"/api/v1/social/friend-request/{request_id}",
            json={"response": "accept"},
            headers={"Authorization": f"Bearer {t2}"},
        )
        assert accept.status_code == 200
        assert accept.json()["success"] is True

        # 验证好友列表
        a_friends = client.get(f"/api/v1/social/{a_id}/friends", headers={"Authorization": f"Bearer {t1}"}).json()["friends"]
        b_friends = client.get(f"/api/v1/social/{b_id}/friends", headers={"Authorization": f"Bearer {t2}"}).json()["friends"]
        assert b_id in a_friends
        assert a_id in b_friends

    def test_reject_friend_request(self, client: TestClient, two_users):
        (a_id, t1), (b_id, t2) = two_users

        send = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": a_id,
                "to_alpha_id": b_id,
            },
            headers={"Authorization": f"Bearer {t1}"},
        )
        request_id = send.json()["request_id"]

        reject = client.put(
            f"/api/v1/social/friend-request/{request_id}",
            json={"response": "reject"},
            headers={"Authorization": f"Bearer {t2}"},
        )
        assert reject.status_code == 200

        a_friends = client.get(f"/api/v1/social/{a_id}/friends", headers={"Authorization": f"Bearer {t1}"}).json()["friends"]
        b_friends = client.get(f"/api/v1/social/{b_id}/friends", headers={"Authorization": f"Bearer {t2}"}).json()["friends"]
        assert b_id not in a_friends
        assert a_id not in b_friends

    def test_send_message_between_friends(self, client: TestClient, two_users):
        (a_id, t1), (b_id, t2) = two_users

        # 成为好友
        send = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": a_id,
                "to_alpha_id": b_id,
            },
            headers={"Authorization": f"Bearer {t1}"},
        )
        req_id = send.json()["request_id"]
        client.put(
            f"/api/v1/social/friend-request/{req_id}",
            json={"response": "accept"},
            headers={"Authorization": f"Bearer {t2}"},
        )

        # A 发消息给 B
        msg = client.post(
            "/api/v1/social/message",
            json={
                "from_alpha_id": a_id,
                "to_alpha_id": b_id,
                "content": "你好，这是测试消息",
                "message_type": "text",
            },
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert msg.status_code == 200
        assert msg.json()["success"] is True

        # B 查看未读消息
        b_msgs = client.get(
            f"/api/v1/social/{b_id}/messages?unread_only=true",
            headers={"Authorization": f"Bearer {t2}"},
        )
        assert b_msgs.status_code == 200
        assert b_msgs.json()["count"] >= 1
        contents = [m["content"] for m in b_msgs.json()["messages"]]
        assert "你好，这是测试消息" in contents

    def test_send_message_to_non_friend_fails(self, client: TestClient, two_users):
        (a_id, t1), (b_id, _) = two_users
        resp = client.post(
            "/api/v1/social/message",
            json={
                "from_alpha_id": a_id,
                "to_alpha_id": b_id,
                "content": "hello",
            },
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert resp.status_code == 400

    def test_friend_request_duplicate(self, client: TestClient, two_users):
        (a_id, t1), (b_id, _) = two_users
        client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": a_id,
                "to_alpha_id": b_id,
            },
            headers={"Authorization": f"Bearer {t1}"},
        )
        resp = client.post(
            "/api/v1/social/friend-request",
            json={
                "from_alpha_id": a_id,
                "to_alpha_id": b_id,
            },
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert resp.status_code == 400


# ==================================================================
# 3. 风控模块 E2E
# ==================================================================


class TestRiskE2E:
    """风控引擎全量评估 + 独立声纹验证"""

    def test_evaluate_full(self, client: TestClient):
        """全量风控评估 — 设备 + 行为 + 声纹"""
        resp = client.post(
            "/api/v1/risk/evaluate",
            json={
                "device_current": {
                    "hardware_id": "hw-mbp-2024",
                    "ip_address": "192.168.1.100",
                    "location": "北京",
                    "browser_info": "Chrome/120",
                    "screen_resolution": "2560x1600",
                    "first_access_time": "2024-01-01T00:00:00",
                },
                "behavior_current": {
                    "typing_speed": 5.2,
                    "session_time": "00:15:30",
                    "common_words": ["你好", "谢谢"],
                    "error_rate": 0.02,
                    "word_count": 120,
                    "emoji_count": 3,
                    "mouse_movement": 450,
                    "input_pattern": "touch",
                    "language": "zh",
                },
                "voice_data": {
                    "voice_match": 0.92,
                    "habit_match": 0.88,
                    "noise_level": 0.05,
                    "audio_quality": 0.95,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_score" in data
        assert "risk_level" in data
        assert "device_score" in data
        assert "behavior_score" in data
        assert "voice_score" in data
        assert 0 <= data["risk_score"] <= 100

    def test_evaluate_device_only(self, client: TestClient):
        """仅设备指纹 → 行为评分 50 默认，声纹评分 0（无声纹数据）"""
        resp = client.post(
            "/api/v1/risk/evaluate",
            json={
                "device_current": {
                    "hardware_id": "hw-unknown",
                    "ip_address": "10.0.0.1",
                    "location": "未知",
                    "browser_info": "Firefox/120",
                    "screen_resolution": "1920x1080",
                    "first_access_time": "2024-06-01T00:00:00",
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["behavior_score"] == 50.0
        assert data["voice_score"] == 0.0

    def test_evaluate_empty(self, client: TestClient):
        """无任何输入 → device_score=100（首次访问满分）, behavior_score=50, voice_score=0"""
        resp = client.post("/api/v1/risk/evaluate", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["behavior_score"] == 50.0
        assert data["voice_score"] == 0.0
        assert data["device_score"] == 100.0

    def test_voice_verify(self, client: TestClient):
        """独立声纹验证 — 高匹配 → 低声纹分 (有风险)"""
        resp = client.post(
            "/api/v1/risk/voice-verify",
            json={
                "user_id": "Alpha-Test",
                "voice_match": 0.95,
                "habit_match": 0.90,
                "noise_level": 0.02,
                "audio_quality": 0.98,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "voice_score" in data
        assert "risk_score" in data
        assert "risk_level" in data
        # voice_match 0.95 >= 0.9 → 不扣60分；habit_match 0.9 >= 0.8 → 不扣20分
        # noise_level 0.02 ≤ 0.3 → 不扣10分；audio_quality 0.98 ≥ 0.7 → 不扣10分
        # → voice_score = 100
        assert data["voice_score"] == 100.0

    def test_low_voice_match_high_risk(self, client: TestClient):
        """低声纹匹配 → 各项扣分 → voice_score 低"""
        resp = client.post(
            "/api/v1/risk/voice-verify",
            json={
                "user_id": "Alpha-Intruder",
                "voice_match": 0.15,  # < 0.9 → -60
                "habit_match": 0.20,  # < 0.8 → -20
                "noise_level": 0.80,  # > 0.3 → -10
                "audio_quality": 0.30,  # < 0.7 → -10
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["voice_score"] == 0.0  # 扣光
        # risk_score = 100 - 0 = 100 → 危险区
        assert data["risk_level"] == "危险区"


# ==================================================================
# 4. 健康检查
# ==================================================================


class TestHealth:
    def test_health_endpoint(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["service"] == "alpha-id"
