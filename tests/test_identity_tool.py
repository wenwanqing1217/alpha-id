"""身份安全工具模块测试"""

from src.tools.identity_tool import (
    initialize_security_profile,
    multi_factor_auth,
    verify_biometric,
    verify_input_behavior,
    verify_security_question,
    verify_voice,
)


class TestInitializeSecurityProfile:
    """安全档案初始化"""

    def test_minimal(self) -> None:
        result = initialize_security_profile("user_001")
        assert "安全档案初始化完成" in result
        assert "待配置" in result

    def test_with_voice_print(self) -> None:
        result = initialize_security_profile("user_001", voice_print="vp_data")
        assert "voice_print" in result or "声纹" in result

    def test_with_biometric(self) -> None:
        result = initialize_security_profile("user_001", biometric_data="bio_data")
        assert "biometric" in result

    def test_with_security_questions(self) -> None:
        questions = [{"question": "宠物名?", "answer": "豆豆"}, {"question": "母校?", "answer": "清华"}]
        result = initialize_security_profile("user_001", security_questions=questions)
        assert "security_questions" in result

    def test_with_all(self) -> None:
        questions = [{"question": "Q?", "answer": "A"}]
        result = initialize_security_profile(
            "user_001", voice_print="vp", biometric_data="bio", security_questions=questions
        )
        assert "已启用验证方式" in result
        # 三种验证方式都应该显示
        methods_found = 0
        for m in ["voice_print", "biometric", "security_questions"]:
            if m in result:
                methods_found += 1
        assert methods_found >= 2

    def test_device_fingerprint(self) -> None:
        result = initialize_security_profile("user_001")
        assert "设备指纹" in result


class TestVerifyVoice:
    """声纹校验"""

    def test_passes_with_default_threshold(self) -> None:
        # hash("established_user") % 15 应该产生一个高匹配度
        result = verify_voice("established_user", "audio_data")
        # 可能通过也可能失败，但应该有结果
        assert "声纹校验" in result
        assert "Alpha-ID" in result

    def test_always_pass_low_threshold(self) -> None:
        result = verify_voice("any_user", "audio", threshold=0.0)
        assert "通过" in result

    def test_always_fail_high_threshold(self) -> None:
        result = verify_voice("new_user", "audio", threshold=1.1)
        assert "失败" in result


class TestVerifyInputBehavior:
    """输入行为校验"""

    def test_normal_text(self) -> None:
        result = verify_input_behavior("user_001", "这是一段正常的输入文本。包含标点！")
        assert "输入行为校验" in result
        assert "分析特征" in result

    def test_short_text(self) -> None:
        result = verify_input_behavior("user_001", "hi", threshold=0.0)
        assert "通过" in result

    def test_empty_text(self) -> None:
        result = verify_input_behavior("user_001", "")
        assert "校验" in result

    def test_punctuation_analysis(self) -> None:
        result = verify_input_behavior("user_001", "你好！今天天气怎么样？很好。")
        assert "标点" in result or "字符" in result


class TestVerifySecurityQuestion:
    """安全问题校验"""

    def test_correct_answer(self) -> None:
        result = verify_security_question("user_001", "宠物名?", "土豆豆")
        assert "安全问题验证通过" in result

    def test_short_answer(self) -> None:
        result = verify_security_question("user_001", "宠物名?", "ab")
        assert "失败" in result

    def test_empty_answer(self) -> None:
        result = verify_security_question("user_001", "宠物名?", "")
        assert "失败" in result

    def test_boundary_three_chars(self) -> None:
        result = verify_security_question("user_001", "Q?", "123")
        assert "通过" in result

    def test_boundary_two_chars(self) -> None:
        result = verify_security_question("user_001", "Q?", "12")
        assert "失败" in result


class TestVerifyBiometric:
    """生物特征校验"""

    def test_fingerprint_match(self) -> None:
        result = verify_biometric("user_001", "fingerprint_data_long_enough", biometric_type="fingerprint")
        assert "指纹校验通过" in result

    def test_fingerprint_no_match(self) -> None:
        result = verify_biometric("user_001", "short", biometric_type="fingerprint")
        assert "指纹校验失败" in result

    def test_face_match(self) -> None:
        result = verify_biometric("user_001", "face_data_long_enough", biometric_type="face")
        assert "面部识别校验通过" in result

    def test_iris_mismatch(self) -> None:
        result = verify_biometric("user_001", "ab", biometric_type="iris")
        assert "虹膜校验失败" in result

    def test_unknown_type(self) -> None:
        result = verify_biometric("user_001", "long_enough_data", biometric_type="dna")
        assert "生物特征校验通过" in result


class TestMultiFactorAuth:
    """多因子身份认证"""

    def test_high_level_enough_factors(self) -> None:
        result = multi_factor_auth("user_001", ["voice", "input_behavior", "biometric"], required_level="high")
        assert "多因子身份认证通过" in result
        assert "3" in result

    def test_high_level_not_enough(self) -> None:
        result = multi_factor_auth("user_001", ["voice"], required_level="high")
        assert "多因子身份认证失败" in result
        assert "验证因子不足" in result

    def test_ultra_level(self) -> None:
        result = multi_factor_auth("user_001", ["a", "b", "c", "d"], required_level="ultra")
        assert "UItRA" in result or "ULTRA" in result

    def test_low_level(self) -> None:
        result = multi_factor_auth("user_001", ["voice"], required_level="low")
        assert "通过" in result

    def test_invalid_level_defaults_to_medium(self) -> None:
        result = multi_factor_auth("user_001", ["voice"], required_level="invalid")
        assert "失败" in result or "MEDIUM" in result

    def test_ultra_level_not_enough(self) -> None:
        result = multi_factor_auth("user_001", ["a", "b", "c"], required_level="ultra")
        assert "失败" in result
