"""安全工具模块测试"""

import hashlib
import re
from datetime import datetime

from src.tools.security_tool import (
    _safe_str,
    generate_security_report,
    lock_account,
    revoke_device_access,
    set_security_level,
    zero_knowledge_proof,
)


class TestSafeStr:
    """_safe_str 工具函数"""

    def test_none(self) -> None:
        assert _safe_str(None) == ""

    def test_string(self) -> None:
        assert _safe_str("hello") == "hello"

    def test_int(self) -> None:
        assert _safe_str(42) == "42"

    def test_empty(self) -> None:
        assert _safe_str("") == ""


class TestLockAccount:
    """锁定账户"""

    def test_lock_success(self) -> None:
        result = lock_account("user_001", "多次失败登录", lock_duration=60, notify_user=True)
        assert "🔒 账户已锁定" in result
        assert "user_001" in result
        assert "60 分钟" in result
        assert "安全通知已发送" in result

    def test_lock_no_notify(self) -> None:
        result = lock_account("user_002", "可疑操作", lock_duration=30, notify_user=False)
        assert "🔒 账户已锁定" in result
        assert "安全通知" not in result

    def test_lock_different_users(self) -> None:
        r1 = lock_account("alice", "test")
        r2 = lock_account("bob", "test")
        # 不同的锁定ID
        assert re.search(r"锁定ID: (\w+)", r1).group(1) != re.search(r"锁定ID: (\w+)", r2).group(1)

    def test_lock_default_duration(self) -> None:
        result = lock_account("user_003", "违规")
        assert "30 分钟" in result


class TestGenerateSecurityReport:
    """安全报告"""

    def test_summary(self) -> None:
        result = generate_security_report("user_001", report_type="summary")
        assert "安全状况摘要" in result
        assert "A级" in result

    def test_detailed(self) -> None:
        result = generate_security_report("user_001", report_type="detailed")
        assert "详细安全报告" in result
        assert "声纹验证" in result

    def test_audit(self) -> None:
        result = generate_security_report("user_001", report_type="audit")
        assert "审计日志报告" in result
        assert "异常事件" in result

    def test_unknown_type(self) -> None:
        result = generate_security_report("user_001", report_type="invalid")
        assert "报告类型不支持" in result

    def test_custom_time_range(self) -> None:
        result = generate_security_report("user_001", time_range="month")
        assert "安全报告已生成" in result
        assert "month" in result


class TestSetSecurityLevel:
    """安全级别"""

    def test_low(self) -> None:
        result = set_security_level("user_001", level="low")
        assert "低安全级别" in result
        assert "单因子验证" in result

    def test_medium(self) -> None:
        result = set_security_level("user_001", level="medium")
        assert "中安全级别" in result
        assert "双因子验证" in result

    def test_high(self) -> None:
        result = set_security_level("user_001", level="high")
        assert "高安全级别" in result
        assert "三因子验证" in result

    def test_ultra(self) -> None:
        result = set_security_level("user_001", level="ultra")
        assert "极高安全级别" in result
        assert "四因子验证" in result

    def test_invalid_level(self) -> None:
        result = set_security_level("user_001", level="bogus")
        assert "无效的安全级别" in result

    def test_mfa_disabled(self) -> None:
        result = set_security_level("user_001", level="high", require_mfa=False)
        assert "未启用" in result
        assert "已启用" not in result


class TestRevokeDeviceAccess:
    """撤销设备"""

    def test_revoke_success(self) -> None:
        result = revoke_device_access("user_001", "device_abc", "设备丢失")
        assert "设备访问权限已撤销" in result
        assert "user_001" in result
        assert "device_abc" in result

    def test_revoke_diff_ids(self) -> None:
        r1 = revoke_device_access("a", "d1", "r1")
        r2 = revoke_device_access("b", "d2", "r2")
        id1 = re.search(r"撤销ID: (\w+)", r1).group(1)
        id2 = re.search(r"撤销ID: (\w+)", r2).group(1)
        assert id1 != id2


class TestZeroKnowledgeProof:
    """零知识证明"""

    def test_valid_statement(self) -> None:
        result = zero_knowledge_proof("user_001", "我是合法用户", proof_type="identity")
        assert "零知识证明验证通过" in result
        assert "有效" in result
        assert "0字节" in result

    def test_short_statement(self) -> None:
        result = zero_knowledge_proof("user_001", "ab", proof_type="ownership")
        assert "零知识证明验证失败" in result
        assert "无效" in result

    def test_boundary_five_chars(self) -> None:
        result = zero_knowledge_proof("user_001", "12345")
        assert "失败" in result

    def test_boundary_six_chars(self) -> None:
        result = zero_knowledge_proof("user_001", "123456")
        assert "通过" in result
