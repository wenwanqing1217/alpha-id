"""风险评分引擎单元测试"""
import pytest
from core.risk_engine import (
    RiskAssessmentEngine,
    DeviceFingerprint,
    BehaviorFingerprint,
    RiskAssessmentResult,
)


class TestRiskAssessmentEngine:
    """RiskAssessmentEngine 核心逻辑测试"""

    @pytest.fixture
    def engine(self):
        return RiskAssessmentEngine()

    @pytest.fixture
    def baseline_device(self):
        return DeviceFingerprint(
            hardware_id="HW-TEST-001",
            ip_address="192.168.1.100",
            location="北京",
            browser_info="Chrome/120",
            screen_resolution="1920x1080",
            first_access_time="2026-01-01 00:00:00",
        )

    def test_same_device_full_score(self, engine, baseline_device):
        """相同设备应得满分 100"""
        score = engine.calculate_device_score(baseline_device, baseline_device)
        assert score == 100.0

    def test_different_hardware_deduct_30(self, engine, baseline_device):
        """不同硬件ID扣30分"""
        current = DeviceFingerprint(
            hardware_id="HW-TEST-002",
            ip_address="192.168.1.100",
            location="北京",
            browser_info="Chrome/120",
            screen_resolution="1920x1080",
            first_access_time="2026-01-01 00:00:00",
        )
        score = engine.calculate_device_score(current, baseline_device)
        assert score == 70.0

    def test_new_device_no_baseline(self, engine):
        """首次访问的设备默认满分"""
        device = DeviceFingerprint(
            hardware_id="HW-NEW-001",
            ip_address="10.0.0.1",
            location="上海",
            browser_info="Firefox/130",
            screen_resolution="2560x1440",
            first_access_time="2026-06-01 00:00:00",
        )
        score = engine.calculate_device_score(device, None)
        assert score == 100.0

    def test_risk_level_thresholds(self, engine):
        """风险等级边界值测试"""
        assert engine.determine_risk_level(0.0) == "安全区"
        assert engine.determine_risk_level(19.99) == "安全区"
        assert engine.determine_risk_level(20.0) == "警戒区"
        assert engine.determine_risk_level(40.0) == "警戒区"
        assert engine.determine_risk_level(59.99) == "警戒区"
        assert engine.determine_risk_level(60.0) == "危险区"
        assert engine.determine_risk_level(100.0) == "危险区"

    def test_total_risk_calculation(self, engine):
        """总分计算：设备40% + 行为35% + 声纹25%"""
        risk = engine.calculate_total_risk(
            device_score=100.0,
            behavior_score=100.0,
            voice_score=0.0,  # 无声纹验证
        )
        # 100*0.4 + 100*0.35 + 0*0.25 = 75, 风险分 = 100 - 75 = 25
        assert risk == 25.0

    def test_no_voice_returns_zero(self, engine):
        """无声纹数据时应返回0分不抛异常"""
        score = engine.calculate_voice_score(None)
        assert score == 0.0

    def test_high_trust_low_risk(self, engine):
        """全维度满分→风险分极低"""
        risk = engine.calculate_total_risk(100.0, 100.0, 100.0)
        assert risk == 0.0

    def test_no_trust_maximum_risk(self, engine):
        """全维度0分→风险分最高"""
        risk = engine.calculate_total_risk(0.0, 0.0, 0.0)
        assert risk == 100.0

    def test_establish_baseline_on_first_call(self, engine):
        """首次调用建立基线，返回满分"""
        behavior = BehaviorFingerprint(
            typing_speed=5.0,
            common_words=["你好", "谢谢", "好的"],
            error_rate=0.02,
            session_time="14:00",
            word_count=20,
            emoji_count=1
        )
        score = engine.calculate_behavior_score(behavior)
        assert score == 100.0
        assert engine.baseline is not None
        assert engine.baseline['typing_speed'] == 5.0

    def test_action_required_mapping(self, engine):
        """验证行动建议映射正确"""
        assert "无需验证" in engine.get_action_required("安全区", 10.0)
        assert "轻度验证" in engine.get_action_required("警戒区", 25.0)
        assert "中度验证" in engine.get_action_required("警戒区", 50.0)
        assert "严格验证" in engine.get_action_required("危险区", 80.0)

    def test_recommended_verification_mapping(self, engine):
        """验证推荐验证方式映射正确"""
        assert "无需验证" in engine.get_recommended_verification("安全区")
        assert "安全问答" in engine.get_recommended_verification("警戒区")
        assert "强制声纹" in engine.get_recommended_verification("危险区")
