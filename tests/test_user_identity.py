"""Alpha-ID 用户身份管理单元测试"""
import json
import os
import sys

import pytest

# 导入被测试类（需要先设置 COZE_WORKSPACE_PATH）
os.environ["COZE_WORKSPACE_PATH"] = str(os.path.join(os.path.dirname(__file__), ".."))

from core.user_identity import UserIdentityManager, UserProfile


class TestUserIdentityManager:
    """UserIdentityManager 核心逻辑测试"""

    @pytest.fixture
    def manager(self, tmp_path):
        """用临时目录创建 UserIdentityManager"""
        # 设置临时工作路径
        old_path = os.environ.get("COZE_WORKSPACE_PATH")
        os.environ["COZE_WORKSPACE_PATH"] = str(tmp_path)
        m = UserIdentityManager()
        yield m
        # 恢复
        if old_path:
            os.environ["COZE_WORKSPACE_PATH"] = old_path
        else:
            del os.environ["COZE_WORKSPACE_PATH"]

    def test_init_creates_empty_db(self, manager):
        """初始化应创建空的 JSON 数据库"""
        db = manager._load_all()
        assert db["users"] == {}
        assert db["counter"] == 0
        assert db["founder_registered"] is False

    def test_register_normal_user(self, manager):
        """普通用户注册，从 Alpha-001 开始"""
        result = manager.register_user(
            device_fingerprint="DEVICE-TEST-001",
            is_founder=False
        )
        assert result["success"] is True
        assert result["alpha_id"] == "Alpha-001"

        # 第二次注册应为 Alpha-002
        result2 = manager.register_user(
            device_fingerprint="DEVICE-TEST-002",
            is_founder=False
        )
        assert result2["success"] is True
        assert result2["alpha_id"] == "Alpha-002"

    def test_register_founder_with_wrong_code(self, manager):
        """创始人验证码错误应拒绝"""
        result = manager.register_user(
            device_fingerprint="FOUNDER-DEVICE",
            is_founder=True,
            founder_code="WRONG-CODE"
        )
        assert result["success"] is False
        assert "验证码无效" in result["message"]

    def test_register_founder_twice(self, manager):
        """创始人只能注册一次"""
        result1 = manager.register_user(
            device_fingerprint="FOUNDER-DEVICE",
            is_founder=True,
            founder_code="Alpha-1-zx"
        )
        assert result1["success"] is True
        assert result1["alpha_id"] == "Alpha-1"

        result2 = manager.register_user(
            device_fingerprint="ANOTHER-DEVICE",
            is_founder=True,
            founder_code="Alpha-1-zx"
        )
        assert result2["success"] is False

    def test_new_user_status_is_locked(self, manager):
        """新注册用户默认锁定"""
        result = manager.register_user(
            device_fingerprint="DEVICE-TEST",
            is_founder=False
        )
        profile = manager.get_user_profile(result["alpha_id"])
        assert profile["status"] == "locked"

    def test_get_user_profile_nonexistent(self, manager):
        """查询不存在的用户应返回 None"""
        profile = manager.get_user_profile("Alpha-999")
        assert profile is None

    def test_update_device_binding(self, manager):
        """设备绑定更新"""
        result = manager.register_user(
            device_fingerprint="DEVICE-A",
            is_founder=False
        )
        alpha_id = result["alpha_id"]

        update = manager.update_device_binding(alpha_id, "DEVICE-B")
        assert update["success"] is True
        assert "DEVICE-B" in update["devices"]

    def test_sync_cross_device(self, manager):
        """跨设备同步"""
        result = manager.register_user(
            device_fingerprint="DEVICE-A",
            is_founder=False
        )
        alpha_id = result["alpha_id"]

        sync = manager.sync_cross_device(alpha_id, "DEVICE-A", "DEVICE-C")
        assert sync["success"] is True
        assert sync["total_devices"] == 2

    def test_record_session_increments(self, manager):
        """会话记录递增"""
        result = manager.register_user(
            device_fingerprint="DEVICE",
            is_founder=False
        )
        alpha_id = result["alpha_id"]

        session1 = manager.record_session(alpha_id)
        assert session1["total_sessions"] == 1

        session2 = manager.record_session(alpha_id)
        assert session2["total_sessions"] == 2

    def test_statistics(self, manager):
        """统计信息"""
        # 注册几个用户
        manager.register_user("DEVICE-1", is_founder=True, founder_code="Alpha-1-zx")
        manager.register_user("DEVICE-2", is_founder=False)
        manager.register_user("DEVICE-3", is_founder=False)

        stats = manager.get_statistics()
        assert stats["total_users"] == 3
        assert stats["founder_registered"] is True
        assert stats["founder_alpha_id"] == "Alpha-1"
