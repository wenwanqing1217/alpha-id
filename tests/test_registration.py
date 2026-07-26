"""
注册路由单元测试

覆盖 SMS 发送/校验、支付宝人脸认证、DID 生成、注册完成。
使用 TestClient 和临时 SQLite 数据库隔离测试数据。
"""

import os

# 在导入任何模块前设置测试密钥
os.environ.setdefault("AUTH_MASTER_KEY", "test-master-key-256bit-secret-for-unit-tests-only")

import pytest

try:
    from fastapi.testclient import TestClient
    _HAVE_FASTAPI = True
except ImportError:
    TestClient = None
    _HAVE_FASTAPI = False

pytestmark = pytest.mark.skipif(
    not _HAVE_FASTAPI,
    reason="缺少 FastAPI/pydantic 环境",
)


@pytest.fixture(autouse=True)
def _reset_all(tmp_path):
    """每个测试前：重置容器 + 注入临时 SQLite 数据库"""
    from alpha_id.container import Container
    from core.storage_sqlite import SqliteStorage

    container = Container.instance()
    container.reset()
    container.storage = SqliteStorage(str(tmp_path / "test.db"))
    yield


@pytest.fixture
def client():
    from src.main import app

    return TestClient(app)


class TestRegistration:
    """注册流程"""

    def test_send_sms(self, client):
        """发送短信验证码"""
        resp = client.post("/api/v1/register/send-sms", json={"phone": "13800138000"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "demo" in data  # 演示模式返回验证码
        assert len(data["demo"]) == 6

    def test_send_sms_invalid_phone(self, client):
        """无效手机号应返回 400"""
        resp = client.post("/api/v1/register/send-sms", json={"phone": "123"})
        assert resp.status_code == 400

    def test_verify_sms(self, client):
        """发送验证码后应能验证通过"""
        # 先发送
        send = client.post("/api/v1/register/send-sms", json={"phone": "13900139000"})
        code = send.json()["demo"]

        # 再验证
        resp = client.post("/api/v1/register/verify-sms", json={"phone": "13900139000", "code": code})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["phone"] == "13900139000"

    def test_verify_sms_wrong_code(self, client):
        """错误验证码应返回 400"""
        client.post("/api/v1/register/send-sms", json={"phone": "13700137000"})
        resp = client.post("/api/v1/register/verify-sms", json={"phone": "13700137000", "code": "000000"})
        assert resp.status_code == 400

    def test_face_verify(self, client):
        """人脸认证（有密钥走真实模式，无密钥走演示模式）"""
        resp = client.post("/api/v1/register/face-verify", json={"phone": "13800138000"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # 有密钥文件时返回 certifyUrl（真实模式）；无密钥时返回 demo=True
        assert data.get("certifyUrl") or data.get("demo") is True

    def test_generate_did(self, client):
        """生成 DID"""
        resp = client.post("/api/v1/register/generate-did", json={"phone": "13800138000"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        did = data["data"]["did"]
        assert did.startswith("did:aid:")
        assert len(data["data"]["publicKey"]) == 64  # 32字节 hex

    def test_complete_registration(self, client):
        """完成注册"""
        resp = client.post("/api/v1/register/complete", json={"did": "did:aid:test123", "phone": "13800138000"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["did"] == "did:aid:test123"

    def test_full_flow(self, client):
        """完整的注册流程：SMS → 人脸 → DID 生成 → 完成"""
        # 1. SMS
        sms = client.post("/api/v1/register/send-sms", json={"phone": "13600136000"})
        assert sms.status_code == 200
        code = sms.json()["demo"]

        # 2. 验证
        verify = client.post("/api/v1/register/verify-sms", json={"phone": "13600136000", "code": code})
        assert verify.status_code == 200

        # 3. 人脸
        face = client.post("/api/v1/register/face-verify", json={"phone": "13600136000"})
        assert face.status_code == 200
        assert face.json()["success"] is True

        # 4. DID
        did_resp = client.post("/api/v1/register/generate-did", json={"phone": "13600136000"})
        assert did_resp.status_code == 200
        did = did_resp.json()["data"]["did"]

        # 5. 完成
        complete = client.post("/api/v1/register/complete", json={"did": did, "phone": "13600136000"})
        assert complete.status_code == 200
        assert complete.json()["data"]["did"] == did
