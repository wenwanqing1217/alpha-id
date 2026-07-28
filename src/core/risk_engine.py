"""
Alpha-ID 风险评分引擎（无外部依赖）

独立于 langchain 框架的核心业务逻辑，可单独测试。
"""

from datetime import datetime
from typing import Dict, List, Optional

try:
    import numpy as np
except ImportError:
    np = None
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DeviceFingerprint:
    """设备指纹"""

    hardware_id: str
    ip_address: str
    location: str
    browser_info: str
    screen_resolution: str
    first_access_time: str


@dataclass
class BehaviorFingerprint:
    """行为指纹"""

    typing_speed: float = 0.0  # 字符/秒
    common_words: List[str] = None  # 常用词列表
    error_rate: float = 0.0  # 错误率
    session_time: str = "00:00"  # 活跃时间段
    word_count: int = 0  # 平均每句话的字数
    emoji_count: int = 0  # 平均每句话的表情符号数
    mouse_movement: int = 0
    input_pattern: str = ""
    language: str = "zh"


@dataclass
class RiskAssessmentResult:
    """风险评估结果"""

    total_risk_score: float
    device_score: float
    behavior_score: float
    voice_score: float
    risk_level: str  # "safe", "caution", "danger"
    action_required: str
    recommended_verification: str


class RiskAssessmentEngine:
    """风险评估引擎"""

    def __init__(self):
        # 权重配置
        self.device_weight = 0.40
        self.behavior_weight = 0.35
        self.voice_weight = 0.25

        # 阈值配置（初始值，会自适应调整）
        self.safe_threshold = 20.0
        self.caution_threshold = 60.0

        # 用户历史数据（用于自适应学习）
        self.user_history: List[Dict] = []

        # 用户行为基线
        self.baseline: Optional[Dict] = None

    def calculate_device_score(self, current: DeviceFingerprint, baseline: Optional[DeviceFingerprint] = None) -> float:
        """
        计算设备信任分（满分100）

        评分维度：
        - 硬件ID匹配：30分
        - IP段匹配：20分
        - 地理位置：20分
        - 浏览器指纹：15分
        - 首次访问时间：15分
        """
        score = 100.0

        if baseline is None:
            # 首次访问，默认满分
            return score

        # 硬件ID匹配（30分）
        if current.hardware_id != baseline.hardware_id:
            score -= 30

        # IP段匹配（20分）
        if not self._same_ip_segment(current.ip_address, baseline.ip_address):
            score -= 20

        # 地理位置匹配（20分）
        if current.location != baseline.location:
            score -= 20

        # 浏览器指纹匹配（15分）
        if current.browser_info != baseline.browser_info:
            score -= 15

        # 首次访问时间（15分）
        if current.first_access_time != baseline.first_access_time:
            score -= 15

        return max(0.0, score)

    def calculate_behavior_score(self, current: BehaviorFingerprint) -> float:
        """
        计算行为信任分（满分100）

        评分维度：
        - 打字速度匹配度：20分
        - 常用词频率：20分
        - 错别字模式：15分
        - 会话时间规律：20分
        - 对话风格（字数+表情）：15分
        - 操作路径：10分
        """
        if self.baseline is None:
            # 尚未建立基线，使用当前数据建立基线
            self._establish_baseline(current)
            return 100.0

        score = 100.0

        # 打字速度匹配度（20分）
        baseline_typing = self.baseline["typing_speed"]
        typing_diff = abs(current.typing_speed - baseline_typing) / baseline_typing if baseline_typing else 0
        if typing_diff > 0.5:  # 偏差超过50%
            score -= 20
        elif typing_diff > 0.2:  # 偏差超过20%
            score -= 10

        # 常用词频率（20分）
        common_word_overlap = self._calculate_word_overlap(current.common_words)
        if common_word_overlap < 0.5:  # 重叠度低于50%
            score -= 20
        elif common_word_overlap < 0.7:  # 重叠度低于70%
            score -= 10

        # 错别字模式（15分）
        error_diff = abs(current.error_rate - self.baseline["error_rate"])
        if error_diff > 0.1:  # 错误率偏差超过10%
            score -= 15

        # 会话时间规律（20分）
        if not self._same_session_time(current.session_time):
            score -= 20

        # 对话风格（15分）
        base_wc = self.baseline["word_count"] or 1
        base_ec = self.baseline["emoji_count"] or 1
        style_diff = (
            abs(current.word_count - self.baseline["word_count"]) / base_wc
            + abs(current.emoji_count - self.baseline["emoji_count"]) / base_ec
        )
        if style_diff > 0.5:
            score -= 15

        return max(0.0, score)

    def calculate_voice_score(self, voice_data: Optional[Dict] = None) -> float:
        """
        计算声纹信任分（满分100）

        评分维度：
        - 声音特征匹配：60分
        - 语音习惯：20分
        - 环境噪音：10分
        - 音频质量：10分

        注意：如果未进行声纹验证，返回0分
        """
        if voice_data is None:
            return 0.0

        score = 100.0

        # 声音特征匹配（60分）
        if voice_data.get("voice_match", 0) < 0.9:  # 匹配度低于90%
            score -= 60

        # 语音习惯（20分）
        if voice_data.get("habit_match", 0) < 0.8:
            score -= 20

        # 环境噪音（10分）
        if voice_data.get("noise_level", 0) > 0.3:  # 噪音高于30%
            score -= 10

        # 音频质量（10分）
        if voice_data.get("audio_quality", 0) < 0.7:
            score -= 10

        return max(0.0, score)

    def calculate_total_risk(self, device_score: float, behavior_score: float, voice_score: float) -> float:
        """
        计算总风险评分

        公式：
        总风险评分 = 100 - (
            设备信任分 × 40% +
            行为信任分 × 35% +
            声纹信任分 × 25%
        )
        """
        total_trust = (
            device_score * self.device_weight + behavior_score * self.behavior_weight + voice_score * self.voice_weight
        )

        risk_score = 100.0 - total_trust
        logger.info(
            "分数计算: device=%.1f behavior=%.1f voice=%.1f risk=%.1f",
            device_score,
            behavior_score,
            voice_score,
            risk_score,
        )
        return risk_score

    def determine_risk_level(self, risk_score: float) -> str:
        """判断风险等级（返回中文兼容）"""
        if risk_score < self.safe_threshold:
            level = "安全区"
        elif risk_score < self.caution_threshold:
            level = "警戒区"
        else:
            level = "危险区"
        logger.warning(
            "规则触发: risk=%.1f threshold=(safe=%.1f, caution=%.1f) level=%s",
            risk_score,
            self.safe_threshold,
            self.caution_threshold,
            level,
        )
        return level

    def get_action_required(self, risk_level: str, risk_score: float) -> str:
        """获取需要采取的行动"""
        if risk_level in ("安全区", "safe"):
            return "无需验证，直接访问"
        elif risk_level in ("警戒区", "caution"):
            if risk_score < 40:
                return "轻度验证：回答安全问题"
            else:
                return "中度验证：声纹验证"
        else:
            return "严格验证：强制声纹验证 + 安全警报"

    def get_recommended_verification(self, risk_level: str) -> str:
        """获取推荐的验证方式"""
        if risk_level in ("安全区", "safe"):
            return "无需验证"
        elif risk_level in ("警戒区", "caution"):
            return "安全问答或声纹验证"
        else:
            return "强制声纹验证"

    def update_baseline(self, current_behavior: BehaviorFingerprint):
        """更新行为基线"""
        if self.baseline is None:
            self._establish_baseline(current_behavior)
            return

        # 使用指数平滑更新基线
        alpha = 0.3  # 学习率
        self.baseline["typing_speed"] = (
            alpha * current_behavior.typing_speed + (1 - alpha) * self.baseline["typing_speed"]
        )
        self.baseline["error_rate"] = alpha * current_behavior.error_rate + (1 - alpha) * self.baseline["error_rate"]
        self.baseline["word_count"] = alpha * current_behavior.word_count + (1 - alpha) * self.baseline["word_count"]
        self.baseline["emoji_count"] = alpha * current_behavior.emoji_count + (1 - alpha) * self.baseline["emoji_count"]
        self.baseline["common_words"] = current_behavior.common_words

    def adjust_thresholds(self, risk_score: float):
        """自适应调整阈值（纯 Python 实现，无需 numpy）"""
        # 记录历史
        self.user_history.append({"timestamp": datetime.now().isoformat(), "risk_score": risk_score})

        # 每10次访问重新计算阈值
        if len(self.user_history) % 10 == 0 and len(self.user_history) >= 10:
            scores = [h["risk_score"] for h in self.user_history[-10:]]

            # 纯 Python 百分位数计算（无需 numpy）
            sorted_scores = sorted(scores)
            n = len(sorted_scores)
            self.safe_threshold = sorted_scores[max(0, int(n * 0.1))]   # 10% 分位数
            self.caution_threshold = sorted_scores[min(n - 1, int(n * 0.9))]  # 90% 分位数

    def predict_next_risk(self) -> Optional[float]:
        """
        预测下一次访问的风险评分

        使用简单的移动平均法
        """
        if len(self.user_history) < 3:
            return None

        recent_scores = [h["risk_score"] for h in self.user_history[-5:]]
        return sum(recent_scores) / len(recent_scores)

    def _same_ip_segment(self, ip1: str, ip2: str) -> bool:
        """判断两个IP是否在同一个网段"""
        try:
            # 简单判断前三位是否相同
            return ip1.rsplit(".", 1)[0] == ip2.rsplit(".", 1)[0]
        except:  # noqa: E722
            return False

    def _same_session_time(self, time1: str, time2: Optional[str] = None) -> bool:
        """判断会话时间是否一致（相差不超过2小时）"""
        if time2 is None and self.baseline:
            time2 = self.baseline["session_time"]

        if not time1 or not time2:
            return True

        try:
            hour1 = int(time1.split(":")[0])
            hour2 = int(time2.split(":")[0])
            return abs(hour1 - hour2) <= 2
        except:  # noqa: E722
            return True

    def _calculate_word_overlap(self, current_words: List[str]) -> float:
        """计算常用词重叠度"""
        if not self.baseline or not self.baseline.get("common_words"):
            return 1.0

        baseline_words = set(self.baseline["common_words"])
        current_set = set(current_words)

        if not baseline_words:
            return 1.0

        overlap = len(baseline_words & current_set)
        return overlap / len(baseline_words)

    def _establish_baseline(self, behavior: BehaviorFingerprint):
        """建立行为基线"""
        self.baseline = {
            "typing_speed": behavior.typing_speed,
            "error_rate": behavior.error_rate,
            "session_time": behavior.session_time,
            "word_count": behavior.word_count,
            "emoji_count": behavior.emoji_count,
            "common_words": behavior.common_words,
        }
