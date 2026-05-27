"""
Alpha-ID 动态风险评估工具（LangGraph 工具层）

依赖核心引擎 core.risk_engine，提供 @tool 装饰的 LangChain 工具函数。
"""
import json
from datetime import datetime
from typing import Dict, Optional
from dataclasses import asdict

from core.risk_engine import (
    DeviceFingerprint,
    BehaviorFingerprint,
    RiskAssessmentResult,
    RiskAssessmentEngine,
)
from langchain.tools import tool, ToolRuntime


# 全局引擎实例
_engine = RiskAssessmentEngine()


@tool
def assess_risk(
    device_info: Dict,
    behavior_info: Dict,
    voice_data: Optional[Dict] = None,
    runtime: ToolRuntime = None
) -> str:
    """
    评估当前访问的风险等级

    Args:
        device_info: 设备信息，包含 hardware_id, ip_address, location, browser_info, screen_resolution
        behavior_info: 行为信息，包含 typing_speed, common_words, error_rate, session_time, word_count, emoji_count
        voice_data: 声纹数据（可选），包含 voice_match, habit_match, noise_level, audio_quality

    Returns:
        JSON格式的风险评估结果，包含：
        - total_risk_score: 总风险评分（0-100）
        - device_score: 设备信任分（0-100）
        - behavior_score: 行为信任分（0-100）
        - voice_score: 声纹信任分（0-100）
        - risk_level: 风险等级（safe/caution/danger）
        - action_required: 需要采取的行动
        - recommended_verification: 推荐的验证方式
    """
    try:
        # 构建设备指纹
        current_device = DeviceFingerprint(
            hardware_id=device_info.get('hardware_id', ''),
            ip_address=device_info.get('ip_address', ''),
            location=device_info.get('location', ''),
            browser_info=device_info.get('browser_info', ''),
            screen_resolution=device_info.get('screen_resolution', ''),
            first_access_time=datetime.now().isoformat()
        )

        # 构建行为指纹
        current_behavior = BehaviorFingerprint(
            typing_speed=behavior_info.get('typing_speed', 80.0),
            common_words=behavior_info.get('common_words', []),
            error_rate=behavior_info.get('error_rate', 0.0),
            session_time=behavior_info.get('session_time', '12:00'),
            word_count=behavior_info.get('word_count', 20),
            emoji_count=behavior_info.get('emoji_count', 1)
        )

        # 计算设备信任分
        device_score = _engine.calculate_device_score(current_device)

        # 计算行为信任分
        behavior_score = _engine.calculate_behavior_score(current_behavior)

        # 计算声纹信任分
        voice_score = _engine.calculate_voice_score(voice_data)

        # 计算总风险评分
        total_risk_score = _engine.calculate_total_risk(device_score, behavior_score, voice_score)

        # 判断风险等级
        risk_level = _engine.determine_risk_level(total_risk_score)

        # 获取需要采取的行动
        action_required = _engine.get_action_required(risk_level, total_risk_score)

        # 获取推荐的验证方式
        recommended_verification = _engine.get_recommended_verification(risk_level)

        # 更新基线
        _engine.update_baseline(current_behavior)

        # 调整阈值
        _engine.adjust_thresholds(total_risk_score)

        # 构建结果
        result = RiskAssessmentResult(
            total_risk_score=round(total_risk_score, 2),
            device_score=round(device_score, 2),
            behavior_score=round(behavior_score, 2),
            voice_score=round(voice_score, 2),
            risk_level=risk_level,
            action_required=action_required,
            recommended_verification=recommended_verification
        )

        return json.dumps(asdict(result), ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"风险评估失败: {str(e)}",
            "total_risk_score": 100.0,
            "risk_level": "danger",
            "action_required": "系统异常，请稍后重试",
            "recommended_verification": "需要人工验证"
        }, ensure_ascii=False, indent=2)


@tool
def get_risk_statistics(runtime: ToolRuntime = None) -> str:
    """
    获取用户的历史风险统计数据

    Returns:
        JSON格式的统计数据，包含：
        - total_sessions: 总会话次数
        - average_risk_score: 平均风险评分
        - safe_sessions: 安全区会话次数
        - caution_sessions: 警戒区会话次数
        - danger_sessions: 危险区会话次数
        - current_thresholds: 当前阈值
        - predicted_next_risk: 预测的下一次风险评分
    """
    try:
        total_sessions = len(_engine.user_history)

        if total_sessions == 0:
            return json.dumps({
                "total_sessions": 0,
                "message": "暂无历史数据"
            }, ensure_ascii=False, indent=2)

        # 计算统计指标
        risk_scores = [h['risk_score'] for h in _engine.user_history]
        average_risk_score = sum(risk_scores) / len(risk_scores)

        safe_sessions = sum(1 for score in risk_scores if score < _engine.safe_threshold)
        caution_sessions = sum(1 for score in risk_scores
                             if _engine.safe_threshold <= score < _engine.caution_threshold)
        danger_sessions = sum(1 for score in risk_scores if score >= _engine.caution_threshold)

        # 预测下一次风险
        predicted_next_risk = _engine.predict_next_risk()

        result = {
            "total_sessions": total_sessions,
            "average_risk_score": round(average_risk_score, 2),
            "safe_sessions": safe_sessions,
            "caution_sessions": caution_sessions,
            "danger_sessions": danger_sessions,
            "current_thresholds": {
                "safe": round(_engine.safe_threshold, 2),
                "caution": round(_engine.caution_threshold, 2)
            },
            "predicted_next_risk": round(predicted_next_risk, 2) if predicted_next_risk else None,
            "baseline": _engine.baseline
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"获取统计失败: {str(e)}"
        }, ensure_ascii=False, indent=2)
