"""
OrchestratorEngine — Ghost 平台统一调度引擎

合并了 alpha_id/orchestrator.py（数据循环）和 core/orchestrator.py（渠道管理）的能力。

架构：
  TwinBrain（唯一实例）
    ├── 数据循环：Feed / Capture / Obsidian / Feishu / NURO / Evolution
    ├── 渠道适配器：飞书 / Web / 微信 / Telegram
    ├── 后台循环：Memory / Ops / Social
    └── EventBus：本地信号 + Redis Streams

用法：
  from orchestrator.engine import OrchestratorEngine, get_orchestrator

  engine = OrchestratorEngine(alpha_id="Ghost-001")
  engine.register_channel(feishu_adapter)
  engine.register_loop("feed", feed_loop_func, interval=3600)
  engine.start()

  # 或使用全局单例
  engine = get_orchestrator()
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core.event_bus import EventBus, EventType, get_event_bus
from core.twin_brain import TwinBrain, BrainSettings
from core.agent import AgentLoop
from core.settings import settings

logger = logging.getLogger(__name__)

# TERM: OrchestratorEngine — 统一后台循环管理（合并自 alpha_id/orchestrator.py + core/orchestrator.py）


# ── 循环间隔常量（秒） ──

MEMORY_INTERVAL_SECONDS = 300    # 5 分钟
OPS_INTERVAL_SECONDS = 1800      # 30 分钟
THREAD_JOIN_TIMEOUT_SECONDS = 5  # 线程等待超时


# ── ChannelAdapter（从 core/orchestrator.py 迁移） ──


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


# ── 循环注册表 ──


class RegisteredLoop:
    """已注册的后台循环"""

    def __init__(self, name: str, func: Callable, interval: int, enabled: bool = True):
        self.name = name
        self.func = func
        self.interval = interval
        self.enabled = enabled
        self.thread: Optional[threading.Thread] = None


# ── OrchestratorEngine ──


class OrchestratorEngine:
    """
    Ghost 平台统一调度引擎

    职责：
      1. 管理 TwinBrain 生命周期（唯一实例）
      2. 管理渠道适配器（飞书/Web/微信/Telegram）
      3. 管理数据循环（Feed/Capture/Obsidian/Feishu/NURO/Evolution）
      4. 管理后台循环（Memory/Ops/Social）
      5. 统一消息入口（receive）
      6. EventBus 连接（本地信号 + Redis Streams）
    """

    def __init__(
        self,
        alpha_id: str = "Ghost-001",
        loops_enabled: bool = True,
        memory_interval: int = MEMORY_INTERVAL_SECONDS,
        ops_interval: int = OPS_INTERVAL_SECONDS,
    ):
        self.alpha_id = alpha_id
        self._loops_enabled = loops_enabled
        self._memory_interval = memory_interval
        self._ops_interval = ops_interval

        # TwinBrain（惰性初始化，唯一实例）
        self._brain: Optional[Any] = None

        # 渠道适配器注册表
        self._channels: Dict[str, ChannelAdapter] = {}

        # 数据循环注册表
        self._data_loops: Dict[str, RegisteredLoop] = {}

        # 后台循环控制
        self._running = False
        self._threads: List[threading.Thread] = []
        self._stop_event = threading.Event()

        # EventBus
        self._event_bus: EventBus = get_event_bus()

        # 统计
        self._stats = {
            "messages_received": 0,
            "messages_replied": 0,
            "loops_executed": 0,
            "started_at": 0.0,
        }

    # ── TwinBrain 管理 ──

    @property
    def brain(self):
        """获取 TwinBrain 实例（惰性创建）"""
        if self._brain is None:
            agent = AgentLoop(
                alpha_id=self.alpha_id,
                model=settings.llm_model,
            )
            self._brain = TwinBrain(
                alpha_id=self.alpha_id,
                storage=None,
                settings=BrainSettings(
                    use_agent_chat=True,
                    agent_model=settings.llm_model,
                ),
            )
            self._brain._agent = agent
            self._brain.awake()
            logger.info("[%s] TwinBrain 已唤醒", self.alpha_id)
        return self._brain

    # ── 渠道管理 ──

    def register_channel(self, adapter: ChannelAdapter):
        """注册渠道适配器"""
        adapter.set_handler(self.receive)
        self._channels[adapter.name] = adapter
        logger.info("渠道已注册: %s", adapter.name)

    def receive(self, sender_id: str, text: str, channel: str = "unknown", **kwargs) -> Optional[str]:
        """统一消息入口 — 所有渠道调用此方法"""
        self._stats["messages_received"] += 1
        logger.info("[%s] %s: %s", channel, sender_id[:8], text[:50])

        from core.message import Message
        msg = Message.create_chat(
            sender=sender_id,
            recipient=self.alpha_id,
            text=text,
        )

        response = self.brain.receive(msg)

        if response.success:
            reply = response.data.get("reply", "") or response.message
            if reply:
                self._stats["messages_replied"] += 1
                return reply
        else:
            logger.warning("处理失败: %s", response.message)

        return None

    # ── 数据循环管理 ──

    def register_loop(self, name: str, func: Callable, interval: int, enabled: bool = True):
        """注册数据循环"""
        self._data_loops[name] = RegisteredLoop(name, func, interval, enabled)
        logger.info("数据循环已注册: %s (每%d秒)", name, interval)

    # ── 后台循环（Memory/Ops） ──

    def _loop_worker(self, phase: LoopPhase, interval: int, func: Callable):
        """循环工作线程"""
        logger.info("循环启动: %s (每%d秒)", phase.value, interval)
        while not self._stop_event.is_set():
            try:
                func()
                self._stats["loops_executed"] += 1
            except Exception as e:
                logger.error("循环异常 [%s]: %s", phase.value, e)
            self._stop_event.wait(interval)
        logger.info("循环停止: %s", phase.value)

    def _memory_loop(self):
        """记忆整理循环 — 每5分钟"""
        if not self.brain:
            return
        try:
            result = self.brain.think()
            logger.debug("记忆循环: %s", result.get("actions_taken", []))
        except Exception as e:
            logger.warning("记忆循环异常: %s", e)

    def _ops_loop(self):
        """运维巡检循环 — 每30分钟"""
        if self.brain and self.brain.state.value == "error":
            logger.warning("大脑处于异常状态，尝试恢复")
            try:
                self.brain.awake()
            except Exception as e:
                logger.error("恢复失败: %s", e)

        logger.info(
            "统计: 收到=%d 回复=%d 循环=%d",
            self._stats["messages_received"],
            self._stats["messages_replied"],
            self._stats["loops_executed"],
        )

    def _start_background_loops(self):
        """启动 Memory/Ops 后台循环"""
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

    # ── 数据循环启动 ──

    def _start_data_loops(self):
        """启动所有已注册的数据循环"""
        for name, loop in self._data_loops.items():
            if not loop.enabled:
                continue
            t = threading.Thread(
                target=self._data_loop_worker,
                args=(loop,),
                name=f"data-{name}",
                daemon=True,
            )
            t.start()
            loop.thread = t
            self._threads.append(t)
            logger.info("  ✓ 数据循环已启动: %s", name)

    def _data_loop_worker(self, loop: RegisteredLoop):
        """数据循环工作线程"""
        logger.info("数据循环启动: %s (每%d秒)", loop.name, loop.interval)
        while not self._stop_event.is_set():
            try:
                loop.func()
            except Exception as e:
                logger.error("数据循环异常 [%s]: %s", loop.name, e)
            self._stop_event.wait(loop.interval)
        logger.info("数据循环停止: %s", loop.name)

    # ── EventBus 连接 ──

    def _wire_event_bus(self):
        """连接 EventBus 信号"""
        self._event_bus.on(EventType.MEMORY_WRITTEN, self._on_memory_written)
        self._event_bus.on(EventType.AGENT_THOUGHT, self._on_agent_thought)
        self._event_bus.on(EventType.SYSTEM_ERROR, self._on_system_error)

    def _on_memory_written(self, data):
        """记忆写入事件"""
        pass

    def _on_agent_thought(self, data):
        """Agent 思考事件"""
        pass

    def _on_system_error(self, data):
        """系统错误事件"""
        self._stats["errors"] = self._stats.get("errors", 0) + 1

    # ── 生命周期 ──

    def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("OrchestratorEngine 已在运行中")
            return

        logger.info("=" * 60)
        logger.info("OrchestratorEngine 启动 (alpha_id=%s)", self.alpha_id)
        logger.info("=" * 60)

        # 初始化大脑
        _ = self.brain

        # 启动所有渠道
        for name, adapter in self._channels.items():
            try:
                adapter.start()
                logger.info("  ✓ 渠道已启动: %s", name)
            except Exception as e:
                logger.error("渠道启动失败 [%s]: %s", name, e)

        # 连接 EventBus
        self._wire_event_bus()
        self._event_bus.start_consuming()

        # 启动后台循环
        self._stop_event.clear()
        self._running = True
        self._stats["started_at"] = time.time()
        self._start_background_loops()

        # 启动数据循环
        self._start_data_loops()

        logger.info("OrchestratorEngine 启动完成 — 渠道=%d 循环=%d",
                     len(self._channels), len(self._data_loops))

    def stop(self):
        """优雅停止"""
        if not self._running:
            return

        logger.info("OrchestratorEngine 停止中...")
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
            t.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)

        # 停止 EventBus 消费
        self._event_bus.stop_consuming()

        # 大脑休眠
        if self._brain:
            self._brain.sleep()

        self._threads.clear()
        logger.info("OrchestratorEngine 已停止")

    def get_status(self) -> Dict[str, Any]:
        """获取运行状态"""
        return {
            "running": self._running,
            "alpha_id": self.alpha_id,
            "stats": self._stats,
            "channels": list(self._channels.keys()),
            "data_loops": {k: {"enabled": v.enabled, "interval": v.interval}
                          for k, v in self._data_loops.items()},
            "brain_state": self._brain.state.value if self._brain else "uninitialized",
            "threads": {t.name: t.is_alive() for t in self._threads},
        }

    # ── 便捷方法 ──

    def think(self, input_text: str = "") -> Dict[str, Any]:
        """通过大脑思考"""
        if not self._brain:
            return {"success": False, "message": "大脑未初始化"}
        return {"success": True, "result": self._brain.think()}

    def chat(self, user_input: str) -> str:
        """聊天"""
        if self._brain:
            result = self._brain.think()
            return str(result)
        return "系统未就绪"

    def capture_input(self, text: str, source: str = "manual"):
        """采集用户输入"""
        return None  # 由数据循环处理

    def write_note(self, title: str, content: str, **kwargs) -> str:
        """写入 Obsidian 笔记"""
        return ""

    def learn_lesson(self, scenario: str, mistake: str, correction: str, lesson: str, **kwargs):
        """记录教训"""
        return None

    def send_feishu(self, chat_id: str, text: str) -> bool:
        """发送飞书消息"""
        return False

    def handle_feishu_webhook(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """处理飞书 Webhook"""
        return {"code": 1, "msg": "飞书未启用"}


# ── 循环阶段枚举 ──


class LoopPhase(Enum):
    """后台循环阶段"""
    MEMORY = "memory"
    OPS = "ops"
    SOCIAL = "social"


# ── 全局单例 ──


_orchestrator: Optional[OrchestratorEngine] = None


def get_orchestrator(alpha_id: str = None, **kwargs) -> OrchestratorEngine:
    """获取全局 OrchestratorEngine 实例"""
    global _orchestrator
    if _orchestrator is None:
        if alpha_id is None:
            alpha_id = getattr(settings, 'ghost_alpha_id', 'Ghost-001')
        _orchestrator = OrchestratorEngine(alpha_id=alpha_id, **kwargs)
    return _orchestrator
