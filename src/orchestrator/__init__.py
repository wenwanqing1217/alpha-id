"""
Orchestrator Package — Ghost 平台统一调度引擎

公开 API：
  - OrchestratorEngine: 统一调度引擎
  - ChannelAdapter: 渠道适配器基类
  - LoopPhase: 循环阶段枚举
  - get_orchestrator(): 全局单例访问
"""

from orchestrator.engine import (
    ChannelAdapter,
    LoopPhase,
    OrchestratorEngine,
    RegisteredLoop,
    get_orchestrator,
)

__all__ = [
    "OrchestratorEngine",
    "ChannelAdapter",
    "LoopPhase",
    "RegisteredLoop",
    "get_orchestrator",
]
