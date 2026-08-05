"""成长追踪器 — 监听 GROWTH_EVENT，累计成长值，触发精灵进化阶段

设计理念（来自 docs/design/ALPHA_ID_02_模拟盘·数字创世纪.md）：
  "进化不是数值游戏。进化的核心是'用户感觉到精灵越来越聪明、越来越像自己'"

成长值来源（每次任务成功执行 +1）：
  - channel_copy   生成文案
  - video_generate 生成视频
  - video_publish  发布视频
  - douyin         发布抖音
  - shortdramas    短剧预审
  - map            地图查询

进化阶段（6 阶段，对应设计文档）：
  1. 种子     0-9      刚激活
  2. 幼生体   10-49    初次互动
  3. 成长期   50-99    10 次有效交互
  4. 成熟体   100-199  50 次，主项目可用
  5. 完全体   200-499  100 次以上
  6. 超越体   500+     画像完整度 > 80%

成长值持久化到 MemoryStore（tag=growth_stats），不引入新存储。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from core.event_bus import EventBus
    from core.memory_store import MemoryStore

logger = logging.getLogger(__name__)


# ── 进化阶段定义 ──
STAGES = [
    {"name": "种子", "min_exp": 0, "emoji": "🌱"},
    {"name": "幼生体", "min_exp": 10, "emoji": "🥚"},
    {"name": "成长期", "min_exp": 50, "emoji": "🌿"},
    {"name": "成熟体", "min_exp": 100, "emoji": "🌳"},
    {"name": "完全体", "min_exp": 200, "emoji": "✨"},
    {"name": "超越体", "min_exp": 500, "emoji": "🔮"},
]

# ── 成长值奖励 ──
TOOL_EXP_REWARDS = {
    "channel_copy": 2,
    "video_generate": 3,
    "video_publish": 5,
    "douyin": 4,
    "shortdramas": 3,
    "map": 1,
    "shopify": 3,
}

DEFAULT_EXP = 1  # 未识别的工具默认成长值


class GrowthTracker:
    """成长追踪器 — 订阅 GROWTH_EVENT，累计成长值

    持久化策略：成长值存在 MemoryStore，tag=growth_stats，
    key 格式：growth_stats:{alpha_id}
    """

    STATS_KEY_PREFIX = "growth_stats"
    STATS_TAG = "growth_stats"

    def __init__(
        self,
        event_bus: Optional["EventBus"] = None,
        memory_store: Optional["MemoryStore"] = None,
    ) -> None:
        self._event_bus = event_bus
        self._memory = memory_store
        self._subscribed = False
        # 内存缓存：storage 不可用时（轻量嵌入/测试）也能自持状态
        self._cache: Dict[str, Dict[str, Any]] = {}

    def start(self) -> None:
        """订阅 GROWTH_EVENT"""
        if self._event_bus is None or self._subscribed:
            return
        self._event_bus.on("growth.event", self._handle_growth_event)
        self._subscribed = True
        logger.info("GrowthTracker 已订阅 GROWTH_EVENT")

    async def _handle_growth_event(self, data: Dict[str, Any]) -> None:
        """处理成长事件

        事件数据格式：
          {
            "alpha_id": "user_id",
            "tool": "channel_copy",
            "success": True,
            "description": "生成香薰文案",
            "source": "feishu"
          }
        """
        try:
            alpha_id = data.get("alpha_id", "default")
            tool = data.get("tool", "unknown")
            success = data.get("success", True)

            if not success:
                return  # 失败不计成长值

            exp_gained = TOOL_EXP_REWARDS.get(tool, DEFAULT_EXP)
            stats = await self._add_exp(alpha_id, exp_gained, tool, data)

            old_stage = stats.get("stage_index", 0)
            new_stage = self._compute_stage(stats["total_exp"])
            if new_stage > old_stage:
                stats["stage_index"] = new_stage
                stats["stage_name"] = STAGES[new_stage]["name"]
                stats["stage_emoji"] = STAGES[new_stage]["emoji"]
                await self._save_stats(alpha_id, stats)
                logger.info(
                    "进化！%s: %s → %s (exp=%d)",
                    alpha_id,
                    STAGES[old_stage]["name"],
                    STAGES[new_stage]["name"],
                    stats["total_exp"],
                )
                # 发布进化事件（供 DS 看板等订阅）
                if self._event_bus:
                    self._event_bus.emit(
                        "growth.event",
                        {
                            "alpha_id": alpha_id,
                            "type": "evolution",
                            "old_stage": STAGES[old_stage]["name"],
                            "new_stage": STAGES[new_stage]["name"],
                            "total_exp": stats["total_exp"],
                        },
                    )
        except Exception as e:
            logger.error("成长事件处理失败: %s", e, exc_info=True)

    async def _add_exp(
        self, alpha_id: str, exp: int, tool: str, event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """增加成长值，返回更新后的统计"""
        stats = await self._load_stats(alpha_id)
        stats["total_exp"] = stats.get("total_exp", 0) + exp
        stats["total_tasks"] = stats.get("total_tasks", 0) + 1

        # 按工具分类统计
        tool_counts = stats.get("tool_counts", {})
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
        stats["tool_counts"] = tool_counts

        stats["last_task_time"] = time.time()
        stats["last_task_tool"] = tool
        stats["last_task_desc"] = event_data.get("description", "")

        await self._save_stats(alpha_id, stats)
        return stats

    async def _load_stats(self, alpha_id: str) -> Dict[str, Any]:
        """从内存缓存 / MemoryStore 加载成长统计"""
        if alpha_id in self._cache:
            return dict(self._cache[alpha_id])

        if self._memory is None:
            stats = self._default_stats()
            self._cache[alpha_id] = stats
            return stats

        try:
            # 尝试读取已有记录
            records = self._memory.query(
                alpha_id=alpha_id,
                tags=[self.STATS_TAG],
                limit=1,
            )
            if records:
                import json
                stats = json.loads(records[0].content)
                self._cache[alpha_id] = stats
                return stats
        except Exception:
            pass
        stats = self._default_stats()
        self._cache[alpha_id] = stats
        return stats

    async def _save_stats(self, alpha_id: str, stats: Dict[str, Any]) -> None:
        """保存成长统计到内存缓存 + MemoryStore"""
        self._cache[alpha_id] = dict(stats)
        if self._memory is None:
            return
        try:
            import json

            from core.memory_store import AlphaMemory
            mem = AlphaMemory(
                memory_id=f"{self.STATS_KEY_PREFIX}:{alpha_id}",
                alpha_id=alpha_id,
                content=json.dumps(stats, ensure_ascii=False),
                category="growth",
                sensitivity=0,
                source="growth_tracker",
                tags=[self.STATS_TAG],
            )
            self._memory.save(mem)
        except Exception as e:
            logger.debug("成长统计保存失败: %s", e)

    def _compute_stage(self, total_exp: int) -> int:
        """根据总成长值计算进化阶段索引"""
        stage_idx = 0
        for i, stage in enumerate(STAGES):
            if total_exp >= stage["min_exp"]:
                stage_idx = i
        return stage_idx

    def _default_stats(self) -> Dict[str, Any]:
        """默认统计"""
        return {
            "total_exp": 0,
            "total_tasks": 0,
            "tool_counts": {},
            "stage_index": 0,
            "stage_name": STAGES[0]["name"],
            "stage_emoji": STAGES[0]["emoji"],
            "last_task_time": 0,
            "last_task_tool": "",
            "last_task_desc": "",
        }

    def get_stage_info(self, total_exp: int) -> Dict[str, Any]:
        """获取阶段信息（供外部查询）"""
        idx = self._compute_stage(total_exp)
        stage = STAGES[idx]
        next_stage = STAGES[idx + 1] if idx + 1 < len(STAGES) else None
        return {
            "current": stage,
            "next": next_stage,
            "exp_to_next": (next_stage["min_exp"] - total_exp) if next_stage else 0,
            "progress": (
                (total_exp - stage["min_exp"]) / (next_stage["min_exp"] - stage["min_exp"])
                if next_stage
                else 1.0
            ),
        }
