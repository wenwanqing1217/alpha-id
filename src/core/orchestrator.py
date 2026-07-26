"""
MasterOrchestrator —— Ghost 平台中央调度器

职责：
  1. 管理 TwinBrain 生命周期（唤醒/休眠/健康检查）
  2. 运行后台循环（MemoryLoop / OpsLoop / SocialLoop）
  3. 统一消息入口（receive），未来对接 Event Bus
  4. 管理 Channel Adapter（飞书/Web/微信/Telegram）

架构定位：
  Channel Adapters → MasterOrchestrator.receive() → TwinBrain.receive() → AgentLoop
                      ↕
              Background Loops (Memory/Ops/Social)
"""
import logging
import os
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core.settings import settings

logger = logging.getLogger(__name__)


class LoopPhase(Enum):
    """后台循环阶段"""
    MEMORY = "memory"      # 记忆整理（每5分钟）
    OPS = "ops"            # 运维巡检（每30分钟）
    SOCIAL = "social"      # 社交维护（事件驱动）


class ChannelAdapter:
    """渠道适配器基类 — 所有外部渠道统一接口"""

    def __init__(self, name: str):
        self.name = name
        self._on_message: Optional[Callable] = None

    def set_handler(self, handler: Callable):
        """设置消息处理回调"""
        self._on_message = handler

    def send(self, chat_id: str, content: Any) -> bool:
        """发送消息到指定会话（子类实现）"""
        raise NotImplementedError

    def start(self):
        """启动渠道监听"""
        raise NotImplementedError

    def stop(self):
        """停止渠道监听"""
        raise NotImplementedError


class MasterOrchestrator:
    """
    Ghost 平台中央调度器

    用法：
        orch = MasterOrchestrator(alpha_id="Ghost-001")
        orch.register_channel(feishu_adapter)
        orch.start()  # 启动所有渠道 + 后台循环
    """

    def __init__(
        self,
        alpha_id: str,
        storage=None,
        loops_enabled: bool = True,
        memory_interval: int = 300,    # 5分钟
        ops_interval: int = 1800,      # 30分钟
    ):
        self.alpha_id = alpha_id
        self._storage = storage
        self._loops_enabled = loops_enabled
        self._memory_interval = memory_interval
        self._ops_interval = ops_interval

        # 核心大脑（惰性初始化）
        self._brain: Optional[Any] = None

        # 渠道适配器注册表
        self._channels: Dict[str, ChannelAdapter] = {}

        # 后台循环控制
        self._running = False
        self._threads: List[threading.Thread] = []
        self._stop_event = threading.Event()

        # 统计
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
            from core.twin_brain import TwinBrain, BrainSettings
            from core.agent import AgentLoop

            agent = AgentLoop(
                alpha_id=self.alpha_id,
                model=settings.llm_model,
            )

            self._brain = TwinBrain(
                alpha_id=self.alpha_id,
                storage=self._storage,
                settings=BrainSettings(
                    use_agent_chat=True,
                    agent_model=settings.llm_model,
                ),
            )
            self._brain._agent = agent
            self._brain.awake()
            logger.info(f"[{self.alpha_id}] TwinBrain 已唤醒")
        return self._brain

    # ── 渠道管理 ──

    def register_channel(self, adapter: ChannelAdapter):
        """注册渠道适配器"""
        adapter.set_handler(self.receive)
        self._channels[adapter.name] = adapter
        logger.info(f"渠道已注册: {adapter.name}")

    def receive(self, sender_id: str, text: str, channel: str = "unknown", **kwargs) -> Optional[str]:
        """
        统一消息入口 — 所有渠道调用此方法

        Args:
            sender_id: 发送者标识
            text: 消息文本
            channel: 渠道名称
            **kwargs: 渠道特定参数（如 image_bytes）

        Returns:
            回复文本（None 表示不回复）
        """
        self._stats["messages_received"] += 1
        logger.info(f"[{channel}] {sender_id[:8]}: {text[:50]}")

        # 构造统一消息
        from core.message import Message
        msg = Message.create_chat(
            sender=sender_id,
            recipient=self.alpha_id,
            text=text,
        )

        # 通过 TwinBrain 处理
        response = self.brain.receive(msg)

        if response.success:
            reply = response.data.get("reply", "") or response.message
            if reply:
                self._stats["messages_replied"] += 1
                return reply
        else:
            logger.warning(f"处理失败: {response.message}")

        return None

    # ── 后台循环 ──

    def _loop_worker(self, phase: LoopPhase, interval: int, func: Callable):
        """循环工作线程"""
        logger.info(f"循环启动: {phase.value} (每{interval}秒)")
        while not self._stop_event.is_set():
            try:
                func()
                self._stats["loops_executed"] += 1
            except Exception as e:
                logger.error(f"循环异常 [{phase.value}]: {e}")
            self._stop_event.wait(interval)
        logger.info(f"循环停止: {phase.value}")

    def _memory_loop(self):
        """记忆整理循环 — 每5分钟"""
        if not self.brain:
            return
        # 触发大脑的 think() 周期（包含记忆整理）
        try:
            result = self.brain.think()
            logger.debug(f"记忆循环: {result.get('actions_taken', [])}")
        except Exception as e:
            logger.warning(f"记忆循环异常: {e}")

    def _ops_loop(self):
        """运维巡检循环 — 每30分钟"""
        # 健康检查：确保大脑状态正常
        if self.brain and self.brain.state.value == "error":
            logger.warning("大脑处于异常状态，尝试恢复")
            try:
                self.brain.awake()
            except Exception as e:
                logger.error(f"恢复失败: {e}")

        # 统计输出
        logger.info(
            f"📊 统计: 收到={self._stats['messages_received']} "
            f"回复={self._stats['messages_replied']} "
            f"循环={self._stats['loops_executed']}"
        )

    def _start_loops(self):
        """启动所有后台循环"""
        if not self._loops_enabled:
            return

        loops = [
            (LoopPhase.MEMORY, self._memory_interval, self._memory_loop),
            (LoopPhase.OPS, self._ops_interval, self._ops_loop),
        ]

        for phase, interval, func in loops:
            t = threading.Thread(
                target=self._loop_worker,
                args=(phase, interval, func),
                name=f"loop-{phase.value}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)

    # ── 生命周期 ──

    def start(self):
        """启动调度器（所有渠道 + 后台循环）"""
        if self._running:
            return

        self._running = True
        self._stats["started_at"] = time.time()
        self._stop_event.clear()

        # 初始化大脑（唤醒）
        _ = self.brain

        # 启动所有渠道
        for name, adapter in self._channels.items():
            try:
                adapter.start()
                logger.info(f"渠道已启动: {name}")
            except Exception as e:
                logger.error(f"渠道启动失败 [{name}]: {e}")

        # 启动后台循环
        self._start_loops()

        logger.info(f"✅ MasterOrchestrator 已启动: {self.alpha_id}")

    def stop(self):
        """停止调度器"""
        self._running = False
        self._stop_event.set()

        # 停止所有渠道
        for name, adapter in self._channels.items():
            try:
                adapter.stop()
            except Exception:
                pass

        # 等待线程结束
        for t in self._threads:
            t.join(timeout=5)

        # 大脑休眠
        if self._brain:
            self._brain.sleep()

        logger.info(f"🛑 MasterOrchestrator 已停止: {self.alpha_id}")

    def get_stats(self) -> Dict[str, Any]:
        """获取运行统计"""
        return {
            **self._stats,
            "alpha_id": self.alpha_id,
            "channels": list(self._channels.keys()),
            "brain_state": self.brain.state.value if self._brain else "uninitialized",
            "running": self._running,
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


