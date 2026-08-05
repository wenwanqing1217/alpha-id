"""
MasterOrchestrator —— Ghost 平台中央调度器（兼容层）

NOTE: 实际实现已迁移到 orchestrator.engine.OrchestratorEngine。
此文件保留 MasterOrchestrator 类名作为兼容层，内部委托到 OrchestratorEngine。

迁移路径：
  - 所有功能已由 OrchestratorEngine 实现
  - 旧代码 import MasterOrchestrator 仍然有效
  - 新代码请直接使用 OrchestratorEngine
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from core.settings import settings

if TYPE_CHECKING:
    from orchestrator.engine import ChannelAdapter, LoopPhase

logger = logging.getLogger(__name__)


class MasterOrchestrator:
    """
    Ghost 平台中央调度器（兼容层）

    所有功能已迁移到 OrchestratorEngine。此委托类保持向后兼容。
    """

    def __init__(
        self,
        alpha_id: str,
        storage=None,
        loops_enabled: bool = True,
        memory_interval: int = 300,
        ops_interval: int = 1800,
    ):
        # TERM: OrchestratorEngine — 统一后台循环管理
        # Runtime import to avoid circular dependency (core.orchestrator → orchestrator.engine → core.event_bus → core.orchestrator)
        from orchestrator.engine import OrchestratorEngine
        self._engine = OrchestratorEngine(
            alpha_id=alpha_id,
            loops_enabled=loops_enabled,
            memory_interval=memory_interval,
            ops_interval=ops_interval,
        )
        self.alpha_id = alpha_id

        self._running = False
        self._brain: Optional[Any] = None
        self._channels: Dict[str, ChannelAdapter] = {}
        self._threads: List[threading.Thread] = []
        self._stats = {
            "messages_received": 0,
            "messages_replied": 0,
            "loops_executed": 0,
            "started_at": 0.0,
        }

    @property
    def brain(self):
        """获取 TwinBrain 实例（惰性创建）"""
        if self._brain is None:
            self._brain = self._engine.brain
        return self._brain

    # ── 渠道管理（兼容旧 API） ──

    def register_channel(self, adapter: ChannelAdapter):
        """注册渠道适配器"""
        self._channels[adapter.name] = adapter
        self._engine.register_channel(adapter)

    def receive(self, sender_id: str, text: str, channel: str = "unknown", **kwargs) -> Optional[str]:
        """统一消息入口"""
        return self._engine.receive(sender_id, text, channel, **kwargs)

    # ── 后台循环（兼容旧 API） ──

    def _loop_worker(self, phase: LoopPhase, interval: int, func: Callable):
        self._engine._loop_worker(phase, interval, func)

    def _memory_loop(self):
        self._engine._memory_loop()

    def _ops_loop(self):
        self._engine._ops_loop()

    def _start_loops(self):
        self._engine._start_background_loops()

    # ── 生命周期（兼容旧 API） ──

    def start(self):
        """启动调度器"""
        if self._running:
            return
        self._running = True
        self._stats["started_at"] = time.time()
        self._engine._stop_event.clear()

        # 初始化大脑
        _ = self.brain

        # 启动所有渠道
        for name, adapter in self._channels.items():
            try:
                adapter.start()
                logger.info("渠道已启动: %s", name)
            except Exception as e:
                logger.error("渠道启动失败 [%s]: %s", name, e)

        # 启动后台循环
        self._start_loops()

        logger.info("MasterOrchestrator 已启动: %s", self.alpha_id)

    def stop(self):
        """停止调度器"""
        self._running = False
        self._engine._stop_event.set()

        for name, adapter in self._channels.items():
            try:
                adapter.stop()
            except Exception:
                pass

        for t in self._threads:
            t.join(timeout=5)

        if self._brain:
            self._brain.sleep()

        logger.info("MasterOrchestrator 已停止: %s", self.alpha_id)

    def get_stats(self) -> Dict[str, Any]:
        """获取运行统计"""
        engine_stats = self._engine.get_stats()
        return {
            **self._stats,
            **engine_stats,
            "alpha_id": self.alpha_id,
            "channels": list(self._channels.keys()),
        }


# ── 全局实例（单例） ──

_orchestrator: Optional[MasterOrchestrator] = None


def get_orchestrator(alpha_id: str = None, **kwargs) -> MasterOrchestrator:
    """获取全局 MasterOrchestrator 实例"""
    global _orchestrator
    if _orchestrator is None:
        if alpha_id is None:
            alpha_id = settings.ghost_alpha_id
        _orchestrator = MasterOrchestrator(alpha_id=alpha_id, **kwargs)
    return _orchestrator


# ── Lazy re-exports (avoid circular import) ──
# core/__init__.py imports ChannelAdapter, LoopPhase, get_orchestrator
# from this module, but they live in orchestrator.engine.
# We defer the import to runtime to break the cycle:
#   core.orchestrator → orchestrator.engine → core.event_bus → core.orchestrator

def __getattr__(name: str):
    if name in ("ChannelAdapter", "LoopPhase"):
        from orchestrator.engine import ChannelAdapter, LoopPhase
        return {"ChannelAdapter": ChannelAdapter, "LoopPhase": LoopPhase}[name]
    raise AttributeError(f"module 'core.orchestrator' has no attribute {name}")
