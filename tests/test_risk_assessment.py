"""风险评分引擎单元测试"""

import pytest

from core.risk_engine import (
    BehaviorFingerprint,
    DeviceFingerprint,
    RiskAssessmentEngine,
)


class TestRiskAssessmentEngine:
    """RiskAssessmentEngine 核心逻辑测试"""

    @pytest.fixture
    def engine(self):
        return RiskAssessmentEngine()

    @pytest.fixture
    def established_engine(self):
        """已建立基线的引擎"""
        eng = RiskAssessmentEngine()
        # 首次调用建立基线
        eng.calculate_behavior_score(
            BehaviorFingerprint(
                typing_speed=5.0,
                common_words=["你好", "谢谢", "好的"],
                error_rate=0.02,
                session_time="14:00",
                word_count=20,
                emoji_count=1,
            )
        )
        return eng

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

    def test_different_ip_deduct_20(self, engine, baseline_device):
        """不同IP段扣20分"""
        current = DeviceFingerprint(
            hardware_id="HW-TEST-001",
            ip_address="10.0.0.1",
            location="北京",
            browser_info="Chrome/120",
            screen_resolution="1920x1080",
            first_access_time="2026-01-01 00:00:00",
        )
        score = engine.calculate_device_score(current, baseline_device)
        assert score == 80.0

    def test_different_location_deduct_20(self, engine, baseline_device):
        """不同地理位置扣20分"""
        current = DeviceFingerprint(
            hardware_id="HW-TEST-001",
            ip_address="192.168.1.100",
            location="上海",
            browser_info="Chrome/120",
            screen_resolution="1920x1080",
            first_access_time="2026-01-01 00:00:00",
        )
        score = engine.calculate_device_score(current, baseline_device)
        assert score == 80.0

    def test_different_browser_deduct_15(self, engine, baseline_device):
        """不同浏览器扣15分"""
        current = DeviceFingerprint(
            hardware_id="HW-TEST-001",
            ip_address="192.168.1.100",
            location="北京",
            browser_info="Firefox/130",
            screen_resolution="1920x1080",
            first_access_time="2026-01-01 00:00:00",
        )
        score = engine.calculate_device_score(current, baseline_device)
        assert score == 85.0

    def test_different_time_deduct_15(self, engine, baseline_device):
        """不同首次访问时间扣15分"""
        current = DeviceFingerprint(
            hardware_id="HW-TEST-001",
            ip_address="192.168.1.100",
            location="北京",
            browser_info="Chrome/120",
            screen_resolution="1920x1080",
            first_access_time="2025-01-01 00:00:00",
        )
        score = engine.calculate_device_score(current, baseline_device)
        assert score == 85.0

    def test_all_different_device_score_minimum(self, engine, baseline_device):
        """所有维度全不同，应扣到最低 0 分"""
        current = DeviceFingerprint(
            hardware_id="HW-OTHER",
            ip_address="10.0.0.1",
            location="上海",
            browser_info="Firefox/130",
            screen_resolution="2560x1440",
            first_access_time="2025-06-01 00:00:00",
        )
        score = engine.calculate_device_score(current, baseline_device)
        assert score == 0.0

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

    def test_voice_high_quality(self, engine):
        """声纹全维度高匹配应得高分"""
        score = engine.calculate_voice_score(
            {
                "voice_match": 0.95,
                "habit_match": 0.85,
                "noise_level": 0.1,
                "audio_quality": 0.8,
            }
        )
        # 100 - 0 - 0 - 0 - 0 = 100 (全部达标)
        assert score == 100.0

    def test_voice_low_match_deduct_60(self, engine):
        """声纹匹配度低于阈值扣60分"""
        score = engine.calculate_voice_score(
            {
                "voice_match": 0.5,
                "habit_match": 0.9,
                "noise_level": 0.1,
                "audio_quality": 0.9,
            }
        )
        assert score == 40.0

    def test_voice_low_habit_deduct_20(self, engine):
        """语音习惯低于阈值扣20分"""
        score = engine.calculate_voice_score(
            {
                "voice_match": 0.95,
                "habit_match": 0.5,
                "noise_level": 0.1,
                "audio_quality": 0.9,
            }
        )
        assert score == 80.0

    def test_voice_high_noise_deduct_10(self, engine):
        """噪音高于阈值扣10分"""
        score = engine.calculate_voice_score(
            {
                "voice_match": 0.95,
                "habit_match": 0.85,
                "noise_level": 0.5,
                "audio_quality": 0.9,
            }
        )
        assert score == 90.0

    def test_voice_low_quality_deduct_10(self, engine):
        """音频质量低于阈值扣10分"""
        score = engine.calculate_voice_score(
            {
                "voice_match": 0.95,
                "habit_match": 0.85,
                "noise_level": 0.1,
                "audio_quality": 0.5,
            }
        )
        assert score == 90.0

    def test_voice_all_issues_full_deduction(self, engine):
        """声纹全维度不达标，最低0分"""
        score = engine.calculate_voice_score(
            {
                "voice_match": 0.0,
                "habit_match": 0.0,
                "noise_level": 1.0,
                "audio_quality": 0.0,
            }
        )
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
            emoji_count=1,
        )
        score = engine.calculate_behavior_score(behavior)
        assert score == 100.0
        assert engine.baseline is not None
        assert engine.baseline["typing_speed"] == 5.0

    def test_behavior_typing_speed_mismatch_large(self, established_engine):
        """打字速度偏差 >50% 扣20分"""
        current = BehaviorFingerprint(
            typing_speed=10.0,  # 基线5.0, 偏差100% > 50%
            common_words=["你好", "谢谢", "好的"],
            error_rate=0.02,
            session_time="14:00",
            word_count=20,
            emoji_count=1,
        )
        score = established_engine.calculate_behavior_score(current)
        assert score == 80.0

    def test_behavior_typing_speed_mismatch_medium(self, established_engine):
        """打字速度偏差在20%-50%之间，扣10分"""
        current = BehaviorFingerprint(
            typing_speed=6.5,  # 基线5.0, 偏差30% > 20%
            common_words=["你好", "谢谢", "好的"],
            error_rate=0.02,
            session_time="14:00",
            word_count=20,
            emoji_count=1,
        )
        score = established_engine.calculate_behavior_score(current)
        assert score == 90.0

    def test_behavior_common_words_low_overlap(self, established_engine):
        """常用词重叠度低于50%扣20分"""
        current = BehaviorFingerprint(
            typing_speed=5.0,
            common_words=["foo", "bar", "baz"],  # 与基线["你好","谢谢","好的"] 重叠0%
            error_rate=0.02,
            session_time="14:00",
            word_count=20,
            emoji_count=1,
        )
        score = established_engine.calculate_behavior_score(current)
        assert score == 80.0

    def test_behavior_common_words_medium_overlap(self, established_engine):
        """常用词重叠度在50%-70%之间，扣10分"""
        # 建立新基线，3个词中2个重叠 ≈ 67%
        eng = RiskAssessmentEngine()
        eng.calculate_behavior_score(
            BehaviorFingerprint(
                typing_speed=5.0,
                common_words=["你好", "谢谢", "好的"],
                error_rate=0.02,
                session_time="14:00",
                word_count=20,
                emoji_count=1,
            )
        )
        current = BehaviorFingerprint(
            typing_speed=5.0,
            common_words=["你好", "谢谢", "再见"],  # 2/3 ≈ 67%
            error_rate=0.02,
            session_time="14:00",
            word_count=20,
            emoji_count=1,
        )
        score = eng.calculate_behavior_score(current)
        assert score == 90.0  # 只扣常问词10分

    def test_behavior_error_rate_mismatch(self, established_engine):
        """错误率偏差超过10%扣15分"""
        current = BehaviorFingerprint(
            typing_speed=5.0,
            common_words=["你好", "谢谢", "好的"],
            error_rate=0.5,  # 基线0.02, 偏差0.48 > 0.1
            session_time="14:00",
            word_count=20,
            emoji_count=1,
        )
        score = established_engine.calculate_behavior_score(current)
        assert score == 85.0

    def test_behavior_session_time_mismatch(self, established_engine):
        """会话时间超过2小时偏差扣20分"""
        current = BehaviorFingerprint(
            typing_speed=5.0,
            common_words=["你好", "谢谢", "好的"],
            error_rate=0.02,
            session_time="20:00",  # 基线14:00, 偏差6小时 > 2小时
            word_count=20,
            emoji_count=1,
        )
        score = established_engine.calculate_behavior_score(current)
        assert score == 80.0

    def test_behavior_style_mismatch(self, established_engine):
        """对话风格偏差超过50%扣15分"""
        current = BehaviorFingerprint(
            typing_speed=5.0,
            common_words=["你好", "谢谢", "好的"],
            error_rate=0.02,
            session_time="14:00",
            word_count=100,  # 基线20, 偏差400%
            emoji_count=10,  # 基线1, 偏差900%
        )
        score = established_engine.calculate_behavior_score(current)
        # 风格偏差: abs(100-20)/20 + abs(10-1)/1 = 4.0 + 9.0 = 13.0 > 0.5 => 扣15
        assert score == 85.0

    def test_behavior_zero_baseline_avoids_zerodiv(self, established_engine):
        """基线单词数或表情数为0时不应除零"""
        eng = RiskAssessmentEngine()
        eng.baseline = {
            "typing_speed": 0.0,
            "error_rate": 0.0,
            "session_time": "14:00",
            "word_count": 0,
            "emoji_count": 0,
            "common_words": [],
        }
        current = BehaviorFingerprint(
            typing_speed=5.0,
            common_words=["你好"],
            error_rate=0.1,
            session_time="15:00",
            word_count=10,
            emoji_count=2,
        )
        score = eng.calculate_behavior_score(current)
        assert score >= 0  # 不应抛零除异常

    def test_behavior_default_values(self, engine):
        """BehaviorFingerprint 默认值应合法"""
        bf = BehaviorFingerprint(common_words=[])
        assert bf.typing_speed == 0.0
        assert bf.error_rate == 0.0
        assert bf.emoji_count == 0
        assert bf.language == "zh"

    def test_update_baseline_first_time(self, engine):
        """首次 update_baseline 应建立基线"""
        behavior = BehaviorFingerprint(
            typing_speed=4.5,
            common_words=["hello", "world"],
            error_rate=0.01,
            session_time="10:00",
            word_count=15,
            emoji_count=2,
        )
        engine.update_baseline(behavior)
        assert engine.baseline is not None
        assert engine.baseline["typing_speed"] == 4.5

    def test_update_baseline_smoothing(self, established_engine):
        """update_baseline 应使用指数平滑更新"""
        behavior = BehaviorFingerprint(
            typing_speed=10.0,
            common_words=["你好", "谢谢", "好的", "新增词"],
            error_rate=0.05,
            session_time="14:00",
            word_count=30,
            emoji_count=3,
        )
        old_speed = established_engine.baseline["typing_speed"]
        established_engine.update_baseline(behavior)
        # 新值 = 0.3 * 10.0 + 0.7 * 5.0 = 6.5
        assert established_engine.baseline["typing_speed"] == pytest.approx(6.5)
        # common_words 直接替换
        assert "新增词" in established_engine.baseline["common_words"]

    def test_predict_next_risk_insufficient_history(self, engine):
        """历史不足3次应返回None"""
        assert engine.predict_next_risk() is None

    def test_predict_next_risk_with_history(self, engine):
        """有足够历史时应返回移动平均"""
        engine.user_history = [
            {"risk_score": 10.0, "timestamp": "2026-01-01"},
            {"risk_score": 20.0, "timestamp": "2026-01-02"},
            {"risk_score": 30.0, "timestamp": "2026-01-03"},
            {"risk_score": 40.0, "timestamp": "2026-01-04"},
            {"risk_score": 50.0, "timestamp": "2026-01-05"},
        ]
        predicted = engine.predict_next_risk()
        assert predicted == pytest.approx(30.0)  # (10+20+30+40+50)/5

    def test_same_ip_segment_identical(self, engine):
        """相同IP段应返回True"""
        assert engine._same_ip_segment("192.168.1.1", "192.168.1.100") is True

    def test_same_ip_segment_different(self, engine):
        """不同IP段应返回False"""
        assert engine._same_ip_segment("192.168.1.1", "10.0.0.1") is False

    def test_same_ip_segment_invalid(self, engine):
        """无效IP不应抛异常"""
        assert engine._same_ip_segment("not-an-ip", "also-bad") is False

    def test_same_session_time_same_hour(self, engine):
        """同一小时应返回True"""
        assert engine._same_session_time("14:00", "14:30") is True

    def test_same_session_time_within_two_hours(self, engine):
        """相差2小时以内应返回True"""
        assert engine._same_session_time("14:00", "15:30") is True

    def test_same_session_time_exceeds_two_hours(self, engine):
        """相差超过2小时应返回False"""
        assert engine._same_session_time("14:00", "17:01") is False

    def test_same_session_time_none_time(self, engine):
        """空时间应返回True"""
        assert engine._same_session_time("", None) is True

    def test_same_session_time_invalid(self, engine):
        """无效时间格式不应抛异常"""
        assert engine._same_session_time("abc", "def") is True

    def test_same_session_time_with_baseline(self, established_engine):
        """使用基线时间比较"""
        assert established_engine._same_session_time("14:00") is True
        assert established_engine._same_session_time("17:00") is False

    def test_calculate_word_overlap_no_baseline(self, engine):
        """无基线时重叠度应为1.0"""
        assert engine._calculate_word_overlap(["你好"]) == 1.0

    def test_calculate_word_overlap_empty_baseline(self, engine):
        """基线空列表时重叠度应为1.0"""
        engine.baseline = {"common_words": []}
        assert engine._calculate_word_overlap(["你好"]) == 1.0

    def test_calculate_word_overlap_full(self, engine):
        """完整重叠度计算"""
        engine.baseline = {"common_words": ["a", "b", "c"]}
        assert engine._calculate_word_overlap(["a", "b"]) == pytest.approx(2 / 3)
        assert engine._calculate_word_overlap(["d", "e"]) == 0.0
        assert engine._calculate_word_overlap(["a", "b", "c"]) == 1.0

    def test_action_required_mapping(self, engine):
        """验证行动建议映射正确"""
        assert "无需验证" in engine.get_action_required("安全区", 10.0)
        assert "轻度验证" in engine.get_action_required("警戒区", 25.0)
        assert "中度验证" in engine.get_action_required("警戒区", 50.0)
        assert "严格验证" in engine.get_action_required("危险区", 80.0)

    def test_action_required_english_levels(self, engine):
        """英文风险等级也应该工作"""
        assert "无需验证" in engine.get_action_required("safe", 10.0)
        assert "轻度验证" in engine.get_action_required("caution", 25.0)
        assert "严格验证" in engine.get_action_required("danger", 80.0)

    def test_recommended_verification_mapping(self, engine):
        """验证推荐验证方式映射正确"""
        assert "无需验证" in engine.get_recommended_verification("安全区")
        assert "安全问答" in engine.get_recommended_verification("警戒区")
        assert "强制声纹" in engine.get_recommended_verification("危险区")

    def test_recommended_verification_english(self, engine):
        """英文风险等级推荐也应该工作"""
        assert "无需验证" in engine.get_recommended_verification("safe")
        assert "安全问答" in engine.get_recommended_verification("caution")
        assert "强制声纹" in engine.get_recommended_verification("danger")
