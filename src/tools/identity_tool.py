import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from tools.tool_decorator import ToolRuntime, tool

# ⚠️ 重要警告：以下所有验证函数均为模拟/演示实现
# 它们使用 hash(user_id) 生成确定性"匹配度"，不执行任何实际的身份验证
# 在生产环境中，这些函数必须替换为真实的生物识别/行为分析 API 调用
# 当前实现仅用于开发和演示目的，不提供任何真实的安全保障
_MOCK_WARNING = (
    "⚠️⚠️⚠️ 警告：当前为模拟验证模式（MOCK），不提供真实身份认证 ⚠️⚠️⚠️\n"
    "匹配度由 hash(user_id) 确定性生成，与实际输入无关。\n"
    "生产环境必须接入真实声纹/行为/生物识别 API。\n"
    + "=" * 50 + "\n"
)


def _safe_str(value: Any) -> str:
    """安全转换为str"""
    if value is None:
        return ""
    return str(value)


@tool
def initialize_security_profile(
    user_id: str,
    voice_print: str = None,
    biometric_data: str = None,
    security_questions: List[Dict[str, str]] = None,
    runtime: Optional[dict] = None,
) -> str:
    """
    初始化用户安全档案（首次配置）。

    参数:
        user_id: Alpha-ID唯一标识
        voice_print: 声纹特征（可选，后续可录入）
        biometric_data: 生物特征数据（可选，如设备指纹）
        security_questions: 安全问题列表（可选），格式：[{"question": "问题", "answer": "答案"}]

    返回:
        初始化结果
    """
    try:
        # 生成安全档案
        security_profile = {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "status": "active",
            "security_level": "medium",
            "verification_methods": [],
            "failed_attempts": 0,
            "locked_until": None,
        }

        # 添加验证方式
        if voice_print:
            security_profile["verification_methods"].append("voice_print")
        if biometric_data:
            security_profile["verification_methods"].append("biometric")
        if security_questions:
            security_profile["verification_methods"].append("security_questions")
            security_profile["security_questions"] = security_questions

        # 生成设备指纹
        device_fingerprint = hashlib.sha256(
            f"{user_id}_{datetime.now().timestamp()}_{len(security_profile['verification_methods'])}".encode()
        ).hexdigest()
        security_profile["device_fingerprint"] = device_fingerprint

        # 生成安全档案摘要
        summary = f"""✅ 安全档案初始化完成

Alpha-ID: {user_id}
创建时间: {security_profile["created_at"]}
安全级别: {security_profile["security_level"]}
已启用验证方式: {", ".join(security_profile["verification_methods"]) if security_profile["verification_methods"] else "待配置"}
设备指纹: {device_fingerprint[:16]}...

⚠️ 重要提醒：
1. 请完成所有验证方式配置以提升安全级别
2. 首次登录后请在30分钟内完成声纹录入
3. 请设置至少3个安全问题以备不时之需
4. 设备指纹已生成，请勿在公共设备上使用"""

        return summary

    except Exception as e:
        return f"❌ 安全档案初始化失败: {str(e)}"


@tool
def verify_voice(user_id: str, audio_input: str, threshold: float = 0.90, runtime: ToolRuntime = None) -> str:
    """
    声纹校验。

    参数:
        user_id: Alpha-ID唯一标识
        audio_input: 音频输入（base64或音频描述）
        threshold: 匹配阈值（默认0.90，即90%）

    返回:
        校验结果
    """
    try:
        # 模拟声纹匹配计算
        # 实际应该调用专业的声纹识别API

        # 这里我们用一个简单的方式模拟：
        # 根据用户ID和时间生成一个"匹配度"
        base_match = 0.85 + (hash(user_id) % 15) / 100.0  # 85% - 99.9%

        # 根据阈值判断
        if base_match >= threshold:
            return f"""{_MOCK_WARNING}✅ 声纹校验通过（模拟）

Alpha-ID: {user_id}
匹配度: {base_match * 100:.1f}%
校验阈值: {threshold * 100:.0f}%
校验时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

身份确认：本人（模拟）"""
        else:
            return f"""{_MOCK_WARNING}❌ 声纹校验失败（模拟）

Alpha-ID: {user_id}
匹配度: {base_match * 100:.1f}%
校验阈值: {threshold * 100:.0f}%
校验时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

身份确认：非本人或匹配度不足
⚠️ 已记录本次失败尝试"""

    except Exception as e:
        return f"❌ 声纹校验失败: {str(e)}"


@tool
def verify_input_behavior(user_id: str, text_input: str, threshold: float = 0.85, runtime: ToolRuntime = None) -> str:
    """
    输入行为校验（打字节奏、常用语、标点习惯）。

    参数:
        user_id: Alpha-ID唯一标识
        text_input: 用户输入文本
        threshold: 匹配阈值（默认0.85，即85%）

    返回:
        校验结果
    """
    try:
        # 分析输入行为特征
        text_length = len(text_input)
        word_count = len(text_input.split())
        punctuation_count = len(re.findall(r"[^\w\s]", text_input))

        # 计算特征指标
        avg_word_length = text_length / word_count if word_count > 0 else 0
        punctuation_ratio = punctuation_count / text_length if text_length > 0 else 0

        # 模拟行为匹配度（实际应该与历史行为对比）
        base_match = 0.80 + (hash(user_id + str(len(text_input))) % 20) / 100.0

        # 根据阈值判断
        if base_match >= threshold:
            return f"""{_MOCK_WARNING}✅ 输入行为校验通过

Alpha-ID: {user_id}
匹配度: {base_match * 100:.1f}%
校验阈值: {threshold * 100:.0f}%
分析特征:
- 文本长度: {text_length} 字符
- 词汇数量: {word_count} 个
- 标点符号: {punctuation_count} 个
- 平均词长: {avg_word_length:.1f} 字符
- 标点占比: {punctuation_ratio * 100:.1f}%

身份确认：本人"""
        else:
            # 触发二次验证
            return f"""{_MOCK_WARNING}⚠️ 输入行为校验异常，触发二次验证

Alpha-ID: {user_id}
匹配度: {base_match * 100:.1f}%
校验阈值: {threshold * 100:.0f}%
分析特征:
- 文本长度: {text_length} 字符
- 词汇数量: {word_count} 个
- 标点符号: {punctuation_count} 个

⚠️ 匹配度不足，请进行二次验证：
1. 声纹验证
2. 安全问题验证
3. 生物特征验证"""

    except Exception as e:
        return f"❌ 输入行为校验失败: {str(e)}"


@tool
def verify_security_question(
    user_id: str, question: str, answer: str, max_attempts: int = 3, runtime: ToolRuntime = None
) -> str:
    """
    安全问题校验。

    参数:
        user_id: Alpha-ID唯一标识
        question: 安全问题
        answer: 用户答案
        max_attempts: 最大尝试次数（默认3次）

    返回:
        校验结果
    """
    try:
        # 模拟答案匹配（实际应该与存储的答案对比）
        # 这里我们简单判断：如果答案长度>3，就认为正确
        # 实际应该用更严格的方式

        if len(answer) >= 3:
            return f"""{_MOCK_WARNING}✅ 安全问题验证通过

Alpha-ID: {user_id}
问题: {question}
验证时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

身份确认：本人"""
        else:
            return f"""{_MOCK_WARNING}❌ 安全问题验证失败

Alpha-ID: {user_id}
问题: {question}
验证时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

⚠️ 答案不正确，请重试（剩余尝试次数: {max_attempts - 1}）"""

    except Exception as e:
        return f"❌ 安全问题验证失败: {str(e)}"


@tool
def verify_biometric(
    user_id: str, biometric_data: str, biometric_type: str = "fingerprint", runtime: ToolRuntime = None
) -> str:
    """
    生物特征校验（指纹/面部识别）。

    参数:
        user_id: Alpha-ID唯一标识
        biometric_data: 生物特征数据
        biometric_type: 特征类型（fingerprint/face/iris）

    返回:
        校验结果
    """
    try:
        # 模拟生物特征匹配
        # 实际应该调用设备生物识别API

        type_mapping = {"fingerprint": "指纹", "face": "面部识别", "iris": "虹膜"}

        biometric_name = type_mapping.get(biometric_type, "生物特征")

        # 模拟匹配结果
        is_match = len(biometric_data) > 5

        if is_match:
            return f"""{_MOCK_WARNING}✅ {biometric_name}校验通过

Alpha-ID: {user_id}
验证类型: {biometric_name}
验证时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

身份确认：本人"""
        else:
            return f"""{_MOCK_WARNING}❌ {biometric_name}校验失败

Alpha-ID: {user_id}
验证类型: {biometric_name}
验证时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

⚠️ 生物特征不匹配，请重试或使用其他验证方式"""

    except Exception as e:
        return f"❌ {biometric_type}校验失败: {str(e)}"


@tool
def multi_factor_auth(
    user_id: str, factors: List[str], required_level: str = "high", runtime: ToolRuntime = None
) -> str:
    """
    多因子身份认证（综合多种验证方式）。

    参数:
        user_id: Alpha-ID唯一标识
        factors: 验证因子列表，如["voice", "input_behavior", "biometric"]
        required_level: 要求的安全级别（low/medium/high/ultra）

    返回:
        综合认证结果
    """
    try:
        level_requirements = {"low": 1, "medium": 2, "high": 3, "ultra": 4}

        required_factors = level_requirements.get(required_level, 2)
        provided_factors = len(factors)

        if provided_factors >= required_factors:
            # 计算综合匹配度
            avg_score = 0.85 + (hash(user_id + str(provided_factors)) % 14) / 100.0

            return f"""{_MOCK_WARNING}✅ 多因子身份认证通过

Alpha-ID: {user_id}
安全级别: {required_level.upper()}
提供因子数: {provided_factors}
要求因子数: {required_factors}
验证因子: {", ".join(factors)}
综合匹配度: {avg_score * 100:.1f}%
认证时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

身份确认：本人
系统权限: 完全访问"""

        else:
            return f"""{_MOCK_WARNING}❌ 多因子身份认证失败

Alpha-ID: {user_id}
安全级别: {required_level.upper()}
提供因子数: {provided_factors}
要求因子数: {required_factors}
验证因子: {", ".join(factors)}

⚠️ 验证因子不足，请补充至少 {required_factors - provided_factors} 个验证方式"""

    except Exception as e:
        return f"❌ 多因子身份认证失败: {str(e)}"
