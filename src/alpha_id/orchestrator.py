"""
Alpha-ID Master Orchestrator — 总调度器（兼容层）

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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from core.event_bus import EventBus, EventType, get_event_bus

from .exceptions import TransientError, PermanentError, ResourceBusyError
from orchestrator.engine import OrchestratorEngine, ChannelAdapter, LoopPhase

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """总调度器配置"""
    alpha_id: str = "Alpha-001"
    enable_feed: bool = True
    enable_smart_capture: bool = True
    enable_obsidian: bool = False
    enable_feishu: bool = False
    enable_nuro: bool = True
    enable_self_evolution: bool = True
    obsidian_vault_path: str = ""
    git_repos: List[str] = field(default_factory=list)
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feed_fetch_interval: int = 3600
    capture_scan_interval: int = 1800
    obsidian_sync_interval: int = 300
    preference_audit_interval: int = 86400
    nuro_proactive_interval: int = 3600
    feed_config: Dict[str, Any] = field(default_factory=lambda: {
        "hackernews_enabled": True,
        "arxiv_enabled": True,
        "max_items_per_fetch": 20,
        "relevance_threshold": 0.5,
    })


class MasterOrchestrator:
    """
    Alpha-ID 总调度器（兼容层）

    所有功能已迁移到 OrchestratorEngine。此委托类保持向后兼容。
    """

    def __init__(self, config: Optional[OrchestratorConfig] = None, container: Optional[Any] = None):
        self.config = config or OrchestratorConfig()
        self._alpha_id = self.config.alpha_id
        self._container = container

        # 委托到 OrchestratorEngine
        self._engine = OrchestratorEngine(alpha_id=self._alpha_id)

        # 保留子模块引用（兼容旧代码）
        self._feed = None
        self._capture = None
        self._obsidian = None
        self._feishu = None
        self._nuro = None
        self._evolution = None
        self._brain = None
        self._enricher = None
        self._event_bus: EventBus = get_event_bus()
        self._running = False

        # 统计
        self._stats = {
            "started_at": "",
            "feed_cycles": 0,
            "capture_cycles": 0,
            "obsidian_syncs": 0,
            "evolution_cycles": 0,
            "errors": 0,
        }

    # ── 初始化（兼容旧 API） ──

    def _init_container(self):
        if self._container is not None:
            return
        from alpha_id.container import Container
        self._container = Container.instance()

    def _init_brain(self):
        """初始化孪生大脑（委托到 engine）"""
        self._brain = self._engine.brain

    def _init_enricher(self):
        from alpha_id.enrichment.llm_enricher import LLMEnricher
        self._enricher = LLMEnricher()

    def _init_feed(self):
        from alpha_id.feed import AgentFeed, FeedConfig
        cfg = FeedConfig(**self.config.feed_config)
        self._feed = AgentFeed(cfg)
        self._feed.on_new_item(self._on_new_feed_item)

    def _init_smart_capture(self):
        from alpha_id.smart_capture import SmartCapture
        self._capture = SmartCapture(
            llm_enricher=self._enricher,
            memory_store=self._brain.memory if self._brain else None,
        )
        self._capture.on_observation(self._on_new_observation)
        for repo_path in self.config.git_repos:
            self._capture.watch_git_repo(repo_path)

    def _init_obsidian(self):
        from alpha_id.obsidian_bridge import ObsidianBridge
        if self.config.obsidian_vault_path:
            self._obsidian = ObsidianBridge(self.config.obsidian_vault_path)
            self._obsidian.on_change(self._on_obsidian_change)
            if self._capture:
                self._capture.watch_obsidian_vault(self.config.obsidian_vault_path)

    def _init_feishu(self):
        from alpha_id.feishu_bridge import FeishuBridge
        self._feishu = FeishuBridge(
            app_id=self.config.feishu_app_id,
            app_secret=self.config.feishu_app_secret,
            verification_token=self.config.feishu_verification_token,
        )
        self._feishu.on_message(self._on_feishu_message)

    def _init_nuro(self):
        from alpha_id.nuro_bridge import NUROBridge
        from fairy.fairy_brain import FairyBrain

        fairy = None
        try:
            fairy = FairyBrain()
            if not fairy.available:
                fairy = None
        except Exception as e:
            logger.debug("本地小模型不可用: %s", e)

        self._nuro = NUROBridge(
            fairy_brain=fairy,
            alpha_id_agent=None,
            memory_store=self._brain.memory if self._brain else None,
        )
        self._nuro.on_event(self._on_nuro_event)

    def _init_evolution(self):
        from alpha_id.self_evolution import SelfEvolution
        self._evolution = SelfEvolution(
            memory_store=self._brain.memory if self._brain else None,
            llm_enricher=self._enricher,
        )

    def _wire_event_bus(self):
        self._event_bus.on(EventType.MEMORY_WRITTEN, self._on_memory_written)
        self._event_bus.on(EventType.AGENT_THOUGHT, self._on_agent_thought)
        self._event_bus.on(EventType.SYSTEM_ERROR, self._on_system_error)

    # ── 回调处理（兼容旧回调） ──

    def _on_new_feed_item(self, item):
        ctx = self._build_user_context()
        score = self._feed.evaluate_relevance(item, ctx)
        if score >= self.config.feed_config.get("relevance_threshold", 0.5):
            self._event_bus.emit("feed.relevant_item", {
                "item": item.to_dict(), "score": score,
            }, source="orchestrator")
            if self._evolution:
                self._evolution.learn_skill_from_feed(item)
            self._feed.mark_learned(item.id)
        else:
            self._event_bus.emit("feed.discarded", {
                "item_id": item.id, "score": score,
            }, source="orchestrator")

    def _on_new_observation(self, obs):
        if obs.severity >= 0.5:
            self._event_bus.emit("capture.alert", {
                "observation": obs.to_dict(),
            }, source="orchestrator")
            if self._nuro:
                self._nuro.reminder(obs.title)
        if self._brain and self._brain.memory:
            try:
                self._brain.memory.save(
                    content=f"[观察] {obs.title}: {obs.detail}",
                    tags=["observation", obs.type, obs.source],
                    sensitivity=5, source="smart_capture",
                )
            except TransientError as e:
                logger.warning("观察存储暂时失败: %s", e)
            except Exception as e:
                logger.error("观察存储异常: %s", e, exc_info=True)
                self._stats["errors"] += 1

    def _on_obsidian_change(self, event):
        self._event_bus.emit("obsidian.changed", {
            "note": event.note_title, "action": event.action,
        }, source="orchestrator")
        if event.action == "modified" and self._evolution:
            self._evolution.learn_from_correction(
                scenario=f"笔记修改: {event.note_title}",
                mistake="之前的理解可能不准确",
                correction=event.content[:200],
                lesson=f"用户修正了关于 {event.note_title} 的理解",
                category="understanding",
            )

    def _on_feishu_message(self, msg):
        if not self._feishu:
            return
        code_reply = self._feishu.handle_message(msg)
        if code_reply:
            self._feishu.send_message(msg.chat_id, code_reply)
            return
        ctx = self._feishu.extract_work_context([msg])
        if ctx:
            self._event_bus.emit("feishu.work_context", ctx, source="orchestrator")
            if self._brain and self._brain.memory:
                try:
                    self._brain.memory.save(
                        content=f"[工作] {ctx.get('raw_summary', '')[:200]}",
                        tags=["work", "feishu"], sensitivity=3, source="feishu",
                    )
                except TransientError as e:
                    logger.warning("飞书工作上下文存储暂时失败: %s", e)
                except Exception as e:
                    logger.error("飞书工作上下文存储异常: %s", e, exc_info=True)
                    self._stats["errors"] += 1

    def _on_nuro_event(self, event):
        if event.type == "user_activity":
            if self._capture:
                self._capture.capture_user_input(event.content, source="nuro")
        elif event.type == "screen_observed":
            if self._brain and self._brain.memory:
                try:
                    self._brain.memory.save(
                        content=f"[屏幕] {event.content[:200]}",
                        tags=["observation", "screen"], sensitivity=2, source="nuro",
                    )
                except TransientError as e:
                    logger.warning("屏幕观察存储暂时失败: %s", e)
                except Exception as e:
                    logger.error("屏幕观察存储异常: %s", e, exc_info=True)
                    self._stats["errors"] += 1

    def _on_memory_written(self, data):
        pass

    def _on_agent_thought(self, data):
        pass

    def _on_system_error(self, data):
        self._stats["errors"] += 1
        if self._evolution:
            self._evolution.learn_from_correction(
                scenario="系统错误", mistake=str(data)[:200],
                correction="需要排查", lesson=f"系统错误: {str(data)[:100]}", category="system",
            )

    # ── 用户上下文 ──

    def _build_user_context(self) -> Dict[str, Any]:
        ctx = {"languages": [], "domains": [], "current_projects": []}
        if not self._brain:
            return ctx
        try:
            memory = self._brain.memory
            if memory:
                tech_memories = memory.search(query="技术 语言 框架 项目", limit=10)
                for mem in tech_memories:
                    content = mem.get("content", "")
                    if "python" in content.lower():
                        ctx["languages"].append("python")
                    if "typescript" in content.lower() or "javascript" in content.lower():
                        ctx["languages"].append("typescript")
                    if "项目" in content:
                        ctx["current_projects"].append(content[:100])
        except TransientError as e:
            logger.warning("用户上下文构建暂时失败: %s", e)
        except Exception as e:
            logger.error("用户上下文构建异常: %s", e, exc_info=True)
            self._stats["errors"] += 1
        return ctx

    # ── 后台循环（兼容旧循环） ──

    def _loop_feed(self):
        if not self._feed:
            return
        while not self._engine._stop_event.is_set():
            try:
                items = self._feed.fetch_latest()
                logger.info("Feed: 获取 %d 条资讯", len(items))
                self._stats["feed_cycles"] += 1
            except Exception as e:
                logger.error("Feed 循环异常: %s", e)
                self._stats["errors"] += 1
            self._engine._stop_event.wait(self.config.feed_fetch_interval)

    def _loop_capture(self):
        if not self._capture:
            return
        while not self._engine._stop_event.is_set():
            try:
                observations = self._capture.scan()
                if observations:
                    logger.info("Capture: 发现 %d 个观察", len(observations))
                self._stats["capture_cycles"] += 1
            except Exception as e:
                logger.error("Capture 循环异常: %s", e)
                self._stats["errors"] += 1
            self._engine._stop_event.wait(self.config.capture_scan_interval)

    def _loop_obsidian(self):
        if not self._obsidian:
            return
        while not self._engine._stop_event.is_set():
            try:
                events = self._obsidian.scan_changes()
                if events:
                    logger.info("Obsidian: 发现 %d 个变更", len(events))
                self._stats["obsidian_syncs"] += 1
            except Exception as e:
                logger.error("Obsidian 循环异常: %s", e)
                self._stats["errors"] += 1
            self._engine._stop_event.wait(self.config.obsidian_sync_interval)

    def _loop_evolution(self):
        if not self._evolution:
            return
        while not self._engine._stop_event.is_set():
            try:
                needs_review = self._evolution.audit_preferences()
                if needs_review:
                    logger.info("Evolution: %d 个偏好需要重新评估", len(needs_review))
                if self._obsidian:
                    sediment_groups = self._obsidian.find_notes_for_sedimentation(min_notes=3)
                    for topic, paths in sediment_groups.items():
                        self._evolution.sediment_knowledge(
                            topic=topic, note_paths=paths, obsidian_bridge=self._obsidian,
                        )
                self._stats["evolution_cycles"] += 1
            except Exception as e:
                logger.error("Evolution 循环异常: %s", e)
                self._stats["errors"] += 1
            self._engine._stop_event.wait(self.config.preference_audit_interval)

    def _loop_nuro(self):
        if not self._nuro:
            return
        while not self._engine._stop_event.is_set():
            try:
                reminder = self._nuro.proactive_check()
                if reminder:
                    logger.info("NURO: %s", reminder)
            except Exception as e:
                logger.error("NURO 循环异常: %s", e)
                self._stats["errors"] += 1
            self._engine._stop_event.wait(self.config.nuro_proactive_interval)

    def _loop_feishu(self):
        if not self._feishu:
            return
        logger.info("飞书 WebSocket 长连接启动")
        self._feishu.start_websocket(stop_event=self._engine._stop_event)

    # ── 公共 API（兼容旧 API） ──

    def start(self):
        """启动总调度器"""
        if self._running:
            logger.warning("Orchestrator 已在运行中")
            return

        logger.info("=" * 60)
        logger.info("Alpha-ID Master Orchestrator 启动（兼容层 → OrchestratorEngine）")
        logger.info("=" * 60)

        # 初始化核心组件
        self._init_container()
        self._init_brain()
        self._init_enricher()

        # 初始化子模块
        if self.config.enable_feed:
            self._init_feed()
        if self.config.enable_smart_capture:
            self._init_smart_capture()
        if self.config.enable_obsidian and self.config.obsidian_vault_path:
            self._init_obsidian()
        if self.config.enable_feishu and self.config.feishu_app_id:
            self._init_feishu()
        if self.config.enable_nuro:
            self._init_nuro()
        if self.config.enable_self_evolution:
            self._init_evolution()

        # 连接 EventBus
        self._wire_event_bus()
        self._event_bus.start_consuming()

        # 将数据循环注册到 engine
        loop_configs = [
            ("feed", self._loop_feed, self.config.feed_fetch_interval, self.config.enable_feed),
            ("capture", self._loop_capture, self.config.capture_scan_interval, self.config.enable_smart_capture),
            ("obsidian", self._loop_obsidian, self.config.obsidian_sync_interval,
             self.config.enable_obsidian and self._obsidian is not None),
            ("evolution", self._loop_evolution, self.config.preference_audit_interval, self.config.enable_self_evolution),
            ("nuro", self._loop_nuro, self.config.nuro_proactive_interval, self.config.enable_nuro),
            ("feishu", self._loop_feishu, 0, self.config.enable_feishu and self._feishu is not None),
        ]

        for name, target, interval, enabled in loop_configs:
            if enabled:
                self._engine.register_loop(name, target, interval)

        # 启动 engine（管理所有循环 + 渠道）
        self._engine._running = False  # 重置，让 engine.start() 正常执行
        self._engine.start()

        self._running = True
        self._stats["started_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("Orchestrator 启动完成 — %d 个后台循环", len(self._engine._data_loops))

    def stop(self):
        """优雅停止"""
        if not self._running:
            return
        logger.info("Orchestrator 停止中...")
        self._engine.stop()
        if self._brain:
            self._brain.sleep()
        self._running = False
        logger.info("Orchestrator 已停止")

    def get_status(self) -> Dict[str, Any]:
        """获取全局状态"""
        engine_status = self._engine.get_status()
        modules = {}
        if self._feed:
            modules["feed"] = self._feed.get_stats()
        if self._capture:
            modules["capture"] = self._capture.get_stats()
        if self._obsidian:
            modules["obsidian"] = self._obsidian.get_stats()
        if self._feishu:
            modules["feishu"] = self._feishu.get_stats()
        if self._nuro:
            modules["nuro"] = self._nuro.get_stats()
        if self._evolution:
            modules["evolution"] = self._evolution.get_stats()
        if self._brain:
            modules["brain"] = {
                "state": self._brain.state.value,
                "message_count": self._brain._message_count,
            }
        return {
            **engine_status,
            "modules": modules,
        }

    # ── 便捷方法（兼容旧 API） ──

    def think(self, input_text: str = "") -> Dict[str, Any]:
        if not self._brain:
            return {"success": False, "message": "大脑未初始化"}
        return {"success": True, "result": self._brain.think()}

    def chat(self, user_input: str) -> str:
        if self._nuro:
            return self._nuro.chat(user_input)
        if self._brain:
            result = self._brain.think()
            return str(result)
        return "系统未就绪"

    def capture_input(self, text: str, source: str = "manual"):
        if self._capture:
            return self._capture.capture_user_input(text, source)
        return None

    def write_note(self, title: str, content: str, **kwargs) -> str:
        if self._obsidian:
            return self._obsidian.write_note(title, content, **kwargs)
        return ""

    def learn_lesson(self, scenario: str, mistake: str, correction: str, lesson: str, **kwargs):
        if self._evolution:
            return self._evolution.learn_from_correction(
                scenario=scenario, mistake=mistake, correction=correction, lesson=lesson, **kwargs,
            )
        return None

    def send_feishu(self, chat_id: str, text: str) -> bool:
        if self._feishu:
            return self._feishu.send_message(chat_id, text)
        return False

    def handle_feishu_webhook(self, body: Dict[str, Any]) -> Dict[str, Any]:
        if self._feishu:
            return self._feishu.handle_webhook(body)
        return {"code": 1, "msg": "飞书未启用"}

    # ── 属性（兼容旧 API） ──

    @property
    def brain(self):
        return self._brain

    @property
    def feed(self):
        return self._feed

    @property
    def capture(self):
        return self._capture

    @property
    def obsidian(self):
        return self._obsidian

    @property
    def feishu(self):
        return self._feishu

    @property
    def nuro(self):
        return self._nuro

    @property
    def evolution(self):
        return self._evolution
