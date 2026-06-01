"""
信誉图谱引擎 —— 基于可观察行为计算 Alpha-ID 信誉评分。

评分维度（每项 0-100）：
- 活跃度 (Activity): 在线时长、消息处理频率
- 社交度 (Social): 好友数量、好友请求接受率
- 消息质量 (Quality): 收发消息比、回复率
- 稳定性 (Stability): 运行时长、错误计数（反向）

综合评分 = 0.30×活跃度 + 0.25×社交度 + 0.25×消息质量 + 0.20×稳定性

评分数据持久化，跨重启不变。
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from core.storage import StorageBackend


@dataclass
class ReputationScore:
    """单次信誉评分快照"""

    alpha_id: str
    composite: float  # 综合评分 0-100
    activity: float  # 活跃度 0-100
    social: float  # 社交度 0-100
    quality: float  # 消息质量 0-100
    stability: float  # 稳定性 0-100
    timestamp: float  # Unix 时间戳
    level: str = ""  # 等级标签

    def __post_init__(self):
        if not self.level:
            self.level = self._compute_level(self.composite)

    @staticmethod
    def _compute_level(composite: float) -> str:
        if composite >= 90:
            return "S"
        elif composite >= 75:
            return "A"
        elif composite >= 55:
            return "B"
        elif composite >= 35:
            return "C"
        else:
            return "D"

    def to_dict(self) -> Dict:
        return {
            "alpha_id": self.alpha_id,
            "composite": round(self.composite, 1),
            "activity": round(self.activity, 1),
            "social": round(self.social, 1),
            "quality": round(self.quality, 1),
            "stability": round(self.stability, 1),
            "level": self.level,
            "timestamp": self.timestamp,
        }


# 存储键
_STORAGE_KEY = "reputation_data"


class ReputationEngine:
    """
    信誉图谱引擎。

    用法：
        engine = ReputationEngine(alpha_id="Alpha-001", storage=storage)
        score = engine.compute(active_hours=12, friend_count=5, ...)
        history = engine.get_history()
    """

    def __init__(self, alpha_id: str, storage: Optional[StorageBackend] = None):
        self.alpha_id = alpha_id
        self._storage = storage

    # ── 数据持久化 ──

    def _load_data(self) -> Dict:
        """加载持久化的信誉数据"""
        if self._storage is None:
            return {}
        data = self._storage.load(_STORAGE_KEY) or {}
        return data.get(self.alpha_id, {})

    def _save_data(self, data: Dict):
        """持久化信誉数据"""
        if self._storage is None:
            return
        all_data = self._storage.load(_STORAGE_KEY) or {}
        all_data[self.alpha_id] = data
        self._storage.save(_STORAGE_KEY, all_data)

    # ── 评分计算 ──

    def compute(
        self,
        *,
        active_hours: float = 0.0,  # 累计活跃小时数
        total_uptime_hours: float = 0.0,  # 总存在时长（小时）
        friend_count: int = 0,  # 好友数量
        friend_accept_rate: float = 1.0,  # 好友请求接受率 0-1
        messages_sent: int = 0,  # 发送消息数
        messages_received: int = 0,  # 接收消息数
        error_count: int = 0,  # 错误计数
        is_awake: bool = False,  # 当前是否活跃
    ) -> ReputationScore:
        """
        计算综合信誉评分。

        所有参数可来自 TwinBrain 运行时数据 + AlphaSocial 快照。
        """
        # 1. 活跃度: 活跃小时数每 6 小时 = 30 分，上限 100
        activity = min(100.0, (active_hours / 6.0) * 30.0)
        if is_awake:
            activity = max(activity, 15.0)  # 在线保底

        # 2. 社交度: 好友数每个 5 分，上限 50；接受率占 50
        social_friend = min(50.0, friend_count * 5.0)
        social_accept = friend_accept_rate * 50.0
        social = social_friend + social_accept

        # 3. 消息质量: 收发比接近 1:1 最好
        total_msgs = messages_sent + messages_received
        if total_msgs > 0:
            ratio = messages_sent / total_msgs  # 0-1, 0.5 最优
            quality = 100.0 - abs(ratio - 0.5) * 200.0  # ratio=0.5→100, ratio=0→0
        else:
            quality = 0.0

        # 4. 稳定性: 低错误 + 长寿命
        if total_uptime_hours > 0:
            life_score = min(50.0, total_uptime_hours / 24.0 * 10.0)  # 每 24h 得 10
        else:
            life_score = 0.0
        if error_count == 0:
            error_score = 50.0
        else:
            error_score = max(0.0, 50.0 - error_count * 10.0)
        stability = life_score + error_score

        # 综合权重
        composite = 0.30 * activity + 0.25 * social + 0.25 * quality + 0.20 * stability

        score = ReputationScore(
            alpha_id=self.alpha_id,
            composite=composite,
            activity=activity,
            social=social,
            quality=quality,
            stability=stability,
            timestamp=time.time(),
        )

        # 持久化
        self._save_score(score)
        return score

    def _save_score(self, score: ReputationScore):
        """保存评分到历史"""
        data = self._load_data()
        history = data.get("history", [])
        history.append(
            {
                "composite": score.composite,
                "activity": score.activity,
                "social": score.social,
                "quality": score.quality,
                "stability": score.stability,
                "timestamp": score.timestamp,
                "level": score.level,
            }
        )
        # 只保留最近 100 条
        if len(history) > 100:
            history = history[-100:]
        data["history"] = history
        data["latest"] = score.to_dict()
        self._save_data(data)

    def get_latest(self) -> Optional[ReputationScore]:
        """获取最近一次评分"""
        data = self._load_data()
        latest = data.get("latest")
        if latest is None:
            return None
        return ReputationScore(
            alpha_id=self.alpha_id,
            composite=latest["composite"],
            activity=latest["activity"],
            social=latest["social"],
            quality=latest["quality"],
            stability=latest["stability"],
            timestamp=latest["timestamp"],
        )

    def get_history(self, limit: int = 20) -> List[Dict]:
        """获取评分历史"""
        data = self._load_data()
        history = data.get("history", [])
        return history[-limit:]

    def get_level(self) -> str:
        """获取当前等级"""
        latest = self.get_latest()
        if latest is None:
            return "N/A"
        return latest.level

    # ── 批量查询 ──

    @staticmethod
    def get_all_scores(storage: StorageBackend) -> Dict[str, Dict]:
        """获取所有 Alpha-ID 的最新信誉评分"""
        data = storage.load(_STORAGE_KEY) or {}
        result = {}
        for alpha_id, record in data.items():
            latest = record.get("latest")
            if latest:
                result[alpha_id] = latest
        return result

    @staticmethod
    def get_leaderboard(storage: StorageBackend, top_n: int = 10) -> List[Dict]:
        """获取信誉排行榜"""
        all_scores = ReputationEngine.get_all_scores(storage)
        sorted_scores = sorted(
            all_scores.values(),
            key=lambda x: x["composite"],
            reverse=True,
        )
        return sorted_scores[:top_n]


# ── Skill reputation scoring (P2-2 归因与信誉图谱) ──


class SkillReputation:
    """技能作者信誉评分——基于归因数据的作者可信度"""

    WEIGHTS = {
        "total_executions": 0.30,  # 使用量越大越可信
        "success_rate": 0.35,  # 成功率越高越可信（最高权重）
        "unique_executors": 0.20,  # 越多不同用户用，说明覆盖面广
        "recency": 0.15,  # 近期活跃度
    }

    @classmethod
    def compute(cls, author_stats: Dict) -> float:
        """
        根据归因统计计算作者信誉分 (0-100)。

        Args:
            author_stats: SkillAttributionTracker.get_author_stats() 的输出
                {"total_executions": int, "success_rate": float, "unique_executors": int, "avg_duration_ms": float}
        """
        # total_executions: 每 20 次执行得 10 分，上限 100
        exec_score = min(100.0, (author_stats.get("total_executions", 0) / 20.0) * 10.0)

        # success_rate: 直接映射 0-100
        success_score = author_stats.get("success_rate", 0.0) * 100.0

        # unique_executors: 每 3 个不同执行者得 10 分，上限 100
        unique_score = min(100.0, (author_stats.get("unique_executors", 0) / 3.0) * 10.0)

        # recency: 如果近期有执行就给分
        recency_score = 50.0 if author_stats.get("total_executions", 0) > 0 else 0.0

        composite = (
            cls.WEIGHTS["total_executions"] * exec_score
            + cls.WEIGHTS["success_rate"] * success_score
            + cls.WEIGHTS["unique_executors"] * unique_score
            + cls.WEIGHTS["recency"] * recency_score
        )

        return round(composite, 1)

    @classmethod
    def compute_level(cls, score: float) -> str:
        if score >= 85:
            return "S"
        elif score >= 70:
            return "A"
        elif score >= 50:
            return "B"
        elif score >= 30:
            return "C"
        else:
            return "D"

    @classmethod
    def format_author_report(cls, author_did: str, author_stats: Dict) -> str:
        """生成作者信誉报告文本"""
        score = cls.compute(author_stats)
        level = cls.compute_level(score)
        lines = [
            f"作者: {author_did[:16]}...",
            f"信誉分: {score}/100 (等级 {level})",
            f"总执行次数: {author_stats.get('total_executions', 0)}",
            f"成功率: {author_stats.get('success_rate', 0.0) * 100:.1f}%",
            f"不同执行者: {author_stats.get('unique_executors', 0)}",
            f"平均执行耗时: {author_stats.get('avg_duration_ms', 0):.0f}ms",
        ]
        return "\n".join(lines)
