"""
Alpha-ID Master Orchestrator — 总调度器
========================================

将所有模块串联成一个有机整体：

  ┌─────────────────────────────────────────────────────────────┐
  │                    Master Orchestrator                       │
  │                                                             │
  │  AgentFeed ──→ evaluate_relevance ──→ learn/sediment       │
  │       │                         │                           │
  │       ▼                         ▼                           │
  │  SelfEvolution ←── lessons ── SmartCapture ──→ observe     │
  │       │                            │                        │
  │       ▼                            ▼                        │
  │  ObsidianBridge ←── notes ── FeishuBridge ──→ work_ctx    │
  │       │                            │                        │
  │       ▼                            ▼                        │
  │  NUROBridge ←── local/cloud ── TwinBrain ──→ think         │
  │       │                            │                        │
  │       └────────── EventBus ─────────┘                        │
  └─────────────────────────────────────────────────────────────┘

核心循环：
  1. Feed 拉取资讯 → 评估相关性 → 学习/沉淀
  2. Capture 扫描产出 → 发现异常 → 触发反馈
  3. Obsidian 读写同步 → 用户修改 = 反馈
  4. Feishu 消息 → 提取工作上下文 → 更新记忆
  5. NURO 观察/聊天 → 本地小模型 + 云端大模型
  6. SelfEvolution 从纠正中学习 → 审视偏好 → 知识沉淀

依赖注入（Phase 2 迁移）：
    # 新用法：注入 container
    container = Container.instance()
    orch = MasterOrchestrator(config, container=container)

    # 旧用法（兼容）：自动取单例
    orch = MasterOrchestrator(config)

异常处理（Phase 2）：
    - 使用新的异常层次：TransientError / PermanentError
    - 不再吞掉异常，至少记录日志
    - 循环内异常不会终止循环，但会上报 EventBus

用法：
    orch = MasterOrchestrator(config, container=container)
    orch.start()           # 启动所有后台循环
    orch.stop()            # 优雅停止
    orch.get_status()      # 获取全局状态
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from core.event_bus import EventBus, EventType, get_event_bus

from .exceptions import TransientError, PermanentError, ResourceBusyError

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """总调度器配置"""
    # 身份
    alpha_id: str = "Alpha-001"

    # 模块开关
    enable_feed: bool = True
    enable_smart_capture: bool = True
    enable_obsidian: bool = False
    enable_feishu: bool = False
    enable_nuro: bool = True
    enable_self_evolution: bool = True

    # 路径
    obsidian_vault_path: str = ""
    git_repos: List[str] = field(default_factory=list)

    # 飞书凭证
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""

    # 抓取间隔（秒）
    feed_fetch_interval: int = 3600       # 资讯抓取：1小时
    capture_scan_interval: int = 1800     # 采集扫描：30分钟
    obsidian_sync_interval: int = 300     # Obsidian同步：5分钟
    preference_audit_interval: int = 86400  # 偏好审视：1天
    nuro_proactive_interval: int = 3600   # NURO主动服务：1小时

    # Feed 配置
    feed_config: Dict[str, Any] = field(default_factory=lambda: {
        "hackernews_enabled": True,
        "arxiv_enabled": True,
        "max_items_per_fetch": 20,
        "relevance_threshold": 0.5,
    })


class MasterOrchestrator:
    """
    Alpha-ID 总调度器

    负责：
    1. 初始化所有子模块
    2. 通过 EventBus 连接模块间通信
    3. 启动后台定时循环
    4. 提供统一的状态查询和控制接口
    """

    def __init__(self, config: Optional[OrchestratorConfig] = None, container: Optional[Any] = None):
        self.config = config or OrchestratorConfig()
        self._alpha_id = self.config.alpha_id

        # 核心组件（延迟初始化）
        # 依赖注入：优先使用传入的 container，否则回退到单例
        self._container = container
        self._brain = None
        self._enricher = None
        self._event_bus: EventBus = get_event_bus()

        # 子模块
        self._feed = None
        self._capture = None
        self._obsidian = None
        self._feishu = None
        self._nuro = None
        self._evolution = None

        # 后台线程
        self._threads: Dict[str, threading.Thread] = {}
        self._stop_event = threading.Event()
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

    # ── 初始化 ──

    def _init_container(self):
        """初始化依赖容器（仅在未注入时取单例）"""
        if self._container is not None:
            return  # 已通过 DI 注入
        from alpha_id.container import Container
        self._container = Container.instance()

    def _init_brain(self):
        """初始化孪生大脑"""
        from core.twin_brain import BrainRegistry
        registry = BrainRegistry()
        self._brain = registry.get_or_create(self._alpha_id, storage=self._container.storage)

    def _init_enricher(self):
        """初始化 LLM 理解引擎"""
        from alpha_id.enrichment.llm_enricher import LLMEnricher
        self._enricher = LLMEnricher()

    def _init_feed(self):
        """初始化资讯采集"""
        from alpha_id.feed import AgentFeed, FeedConfig
        cfg = FeedConfig(**self.config.feed_config)
        self._feed = AgentFeed(cfg)

        # 注册回调：新资讯 → 评估相关性 → 学习
        self._feed.on_new_item(self._on_new_feed_item)

    def _init_smart_capture(self):
        """初始化智能采集"""
        from alpha_id.smart_capture import SmartCapture
        self._capture = SmartCapture(
            llm_enricher=self._enricher,
            memory_store=self._brain.memory if self._brain else None,
        )

        # 注册回调：新观察 → 触发反馈
        self._capture.on_observation(self._on_new_observation)

        # 添加 Git 仓库监控
        for repo_path in self.config.git_repos:
            self._capture.watch_git_repo(repo_path)

    def _init_obsidian(self):
        """初始化 Obsidian 桥接"""
        from alpha_id.obsidian_bridge import ObsidianBridge
        if self.config.obsidian_vault_path:
            self._obsidian = ObsidianBridge(self.config.obsidian_vault_path)
            self._obsidian.on_change(self._on_obsidian_change)
            # 同时让 SmartCapture 监控 Obsidian
            if self._capture:
                self._capture.watch_obsidian_vault(self.config.obsidian_vault_path)

    def _init_feishu(self):
        """初始化飞书桥接"""
        from alpha_id.feishu_bridge import FeishuBridge
        self._feishu = FeishuBridge(
            app_id=self.config.feishu_app_id,
            app_secret=self.config.feishu_app_secret,
            verification_token=self.config.feishu_verification_token,
        )
        self._feishu.on_message(self._on_feishu_message)

    def _init_nuro(self):
        """初始化 NURO 桥接"""
        from alpha_id.nuro_bridge import NUROBridge
        from fairy.fairy_brain import FairyBrain

        # 尝试初始化本地小模型
        fairy = None
        try:
            fairy = FairyBrain()
            if not fairy.available:
                fairy = None
        except Exception as e:
            logger.debug("本地小模型不可用: %s", e)

        self._nuro = NUROBridge(
            fairy_brain=fairy,
            alpha_id_agent=None,  # 通过 brain 直接交互，避免循环引用
            memory_store=self._brain.memory if self._brain else None,
        )
        self._nuro.on_event(self._on_nuro_event)

    def _init_evolution(self):
        """初始化自进化引擎"""
        from alpha_id.self_evolution import SelfEvolution
        self._evolution = SelfEvolution(
            memory_store=self._brain.memory if self._brain else None,
            llm_enricher=self._enricher,
        )

    def _wire_event_bus(self):
        """连接 EventBus 信号"""
        # 记忆写入 → 触发采集扫描
        self._event_bus.on(EventType.MEMORY_WRITTEN, self._on_memory_written)

        # Agent 思考 → 可能触发进化
        self._event_bus.on(EventType.AGENT_THOUGHT, self._on_agent_thought)

        # 系统错误 → 记录教训
        self._event_bus.on(EventType.SYSTEM_ERROR, self._on_system_error)

    # ── 回调处理 ──

    def _on_new_feed_item(self, item):
        """新资讯到达"""
        # 构建用户上下文
        ctx = self._build_user_context()
        score = self._feed.evaluate_relevance(item, ctx)

        if score >= self.config.feed_config.get("relevance_threshold", 0.5):
            # 相关资讯 → 学习
            self._event_bus.emit("feed.relevant_item", {
                "item": item.to_dict(),
                "score": score,
            }, source="orchestrator")

            # 尝试从资讯中学习技能
            if self._evolution:
                self._evolution.learn_skill_from_feed(item)

            # 标记为已学习
            self._feed.mark_learned(item.id)
        else:
            # 不相关资讯 → 丢弃
            self._event_bus.emit("feed.discarded", {
                "item_id": item.id,
                "score": score,
            }, source="orchestrator")

    def _on_new_observation(self, obs):
        """新观察到达"""
        # 严重观察 → 触发反馈
        if obs.severity >= 0.5:
            self._event_bus.emit("capture.alert", {
                "observation": obs.to_dict(),
            }, source="orchestrator")

            # 通过 NURO 提醒用户
            if self._nuro:
                self._nuro.reminder(obs.title)

        # 所有观察 → 存入记忆
        if self._brain and self._brain.memory:
            try:
                self._brain.memory.save(
                    content=f"[观察] {obs.title}: {obs.detail}",
                    tags=["observation", obs.type, obs.source],
                    sensitivity=5,
                    source="smart_capture",
                )
            except TransientError as e:
                logger.warning("观察存储暂时失败（可重试）: %s", e)
                self._stats["errors"] += 1
            except PermanentError as e:
                logger.error("观察存储永久失败: %s", e)
                self._stats["errors"] += 1
            except Exception as e:
                # 兜底：未知异常不吞掉，记录后上报 EventBus
                logger.error("观察存储异常: %s", e, exc_info=True)
                self._stats["errors"] += 1
                self._event_bus.emit(EventType.SYSTEM_ERROR, {
                    "source": "orchestrator._on_new_observation",
                    "error": str(e),
                    "observation_id": getattr(obs, "id", "unknown"),
                }, source="orchestrator")

    def _on_obsidian_change(self, event):
        """Obsidian 笔记变更"""
        self._event_bus.emit("obsidian.changed", {
            "note": event.note_title,
            "action": event.action,
        }, source="orchestrator")

        # 用户修改笔记 = 反馈 → 学习
        if event.action == "modified" and self._evolution:
            # 用户改了笔记内容，说明之前的理解可能有偏差
            self._evolution.learn_from_correction(
                scenario=f"笔记修改: {event.note_title}",
                mistake="之前的理解可能不准确",
                correction=event.content[:200],
                lesson=f"用户修正了关于 {event.note_title} 的理解",
                category="understanding",
            )

    def _on_feishu_message(self, msg):
        """飞书消息到达"""
        if not self._feishu:
            return

        # 代码模式：自动执行编程任务
        code_reply = self._feishu.handle_message(msg)
        if code_reply:
            # 代码模式有回复 → 直接发送结果
            self._feishu.send_message(msg.chat_id, code_reply)
            return

        # 对话模式：提取工作上下文
        ctx = self._feishu.extract_work_context([msg])
        if ctx:
            self._event_bus.emit("feishu.work_context", ctx, source="orchestrator")

            # 更新记忆
            if self._brain and self._brain.memory:
                try:
                    self._brain.memory.save(
                        content=f"[工作] {ctx.get('raw_summary', '')[:200]}",
                        tags=["work", "feishu"],
                        sensitivity=3,
                        source="feishu",
                    )
                except TransientError as e:
                    logger.warning("飞书工作上下文存储暂时失败: %s", e)
                except Exception as e:
                    logger.error("飞书工作上下文存储异常: %s", e, exc_info=True)
                    self._stats["errors"] += 1

    def _on_nuro_event(self, event):
        """NURO 事件"""
        if event.type == "user_activity":
            # 用户活动 → 传给 SmartCapture
            if self._capture:
                self._capture.capture_user_input(event.content, source="nuro")

        elif event.type == "screen_observed":
            # 屏幕观察 → 存入记忆
            if self._brain and self._brain.memory:
                try:
                    self._brain.memory.save(
                        content=f"[屏幕] {event.content[:200]}",
                        tags=["observation", "screen"],
                        sensitivity=2,
                        source="nuro",
                    )
                except TransientError as e:
                    logger.warning("屏幕观察存储暂时失败: %s", e)
                except Exception as e:
                    logger.error("屏幕观察存储异常: %s", e, exc_info=True)
                    self._stats["errors"] += 1

    def _on_memory_written(self, data):
        """记忆写入事件"""
        # 可以在这里触发实时分析
        pass

    def _on_agent_thought(self, data):
        """Agent 思考事件"""
        pass

    def _on_system_error(self, data):
        """系统错误事件"""
        self._stats["errors"] += 1
        if self._evolution:
            self._evolution.learn_from_correction(
                scenario="系统错误",
                mistake=str(data)[:200],
                correction="需要排查",
                lesson=f"系统错误: {str(data)[:100]}",
                category="system",
            )

    # ── 用户上下文 ──

    def _build_user_context(self) -> Dict[str, Any]:
        """从记忆系统构建用户上下文"""
        ctx = {
            "languages": [],
            "domains": [],
            "current_projects": [],
        }

        if not self._brain:
            return ctx

        try:
            memory = self._brain.memory
            if memory:
                # 从记忆中提取技术栈信息
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

    # ── 后台循环 ──

    def _loop_feed(self):
        """资讯抓取循环"""
        while not self._stop_event.is_set():
            try:
                if self._feed:
                    items = self._feed.fetch_latest()
                    logger.info("Feed: 获取 %d 条资讯", len(items))
                    self._stats["feed_cycles"] += 1
            except Exception as e:
                logger.error("Feed 循环异常: %s", e)
                self._stats["errors"] += 1

            # 等待下一次抓取
            self._stop_event.wait(self.config.feed_fetch_interval)

    def _loop_capture(self):
        """采集扫描循环"""
        while not self._stop_event.is_set():
            try:
                if self._capture:
                    observations = self._capture.scan()
                    if observations:
                        logger.info("Capture: 发现 %d 个观察", len(observations))
                    self._stats["capture_cycles"] += 1
            except Exception as e:
                logger.error("Capture 循环异常: %s", e)
                self._stats["errors"] += 1

            self._stop_event.wait(self.config.capture_scan_interval)

    def _loop_obsidian(self):
        """Obsidian 同步循环"""
        while not self._stop_event.is_set():
            try:
                if self._obsidian:
                    events = self._obsidian.scan_changes()
                    if events:
                        logger.info("Obsidian: 发现 %d 个变更", len(events))
                    self._stats["obsidian_syncs"] += 1
            except Exception as e:
                logger.error("Obsidian 循环异常: %s", e)
                self._stats["errors"] += 1

            self._stop_event.wait(self.config.obsidian_sync_interval)

    def _loop_evolution(self):
        """自进化循环"""
        while not self._stop_event.is_set():
            try:
                if self._evolution:
                    # 审视偏好
                    needs_review = self._evolution.audit_preferences()
                    if needs_review:
                        logger.info("Evolution: %d 个偏好需要重新评估", len(needs_review))

                    # 知识沉淀
                    if self._obsidian:
                        sediment_groups = self._obsidian.find_notes_for_sedimentation(min_notes=3)
                        for topic, paths in sediment_groups.items():
                            self._evolution.sediment_knowledge(
                                topic=topic,
                                note_paths=paths,
                                obsidian_bridge=self._obsidian,
                            )

                    self._stats["evolution_cycles"] += 1
            except Exception as e:
                logger.error("Evolution 循环异常: %s", e)
                self._stats["errors"] += 1

            self._stop_event.wait(self.config.preference_audit_interval)

    def _loop_nuro(self):
        """NURO 主动服务循环"""
        while not self._stop_event.is_set():
            try:
                if self._nuro:
                    reminder = self._nuro.proactive_check()
                    if reminder:
                        logger.info("NURO: %s", reminder)
            except Exception as e:
                logger.error("NURO 循环异常: %s", e)
                self._stats["errors"] += 1

            self._stop_event.wait(self.config.nuro_proactive_interval)

    def _loop_feishu(self):
        """飞书 WebSocket 长连接循环"""
        if not self._feishu:
            return
        logger.info("飞书 WebSocket 长连接启动")
        self._feishu.start_websocket(stop_event=self._stop_event)

    # ── 公共 API ──

    def start(self):
        """启动总调度器"""
        if self._running:
            logger.warning("Orchestrator 已在运行中")
            return

        logger.info("=" * 60)
        logger.info("Alpha-ID Master Orchestrator 启动")
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

        # 连接 EventBus（本地信号 + Redis Streams）
        self._wire_event_bus()
        self._event_bus.start_consuming()

        # 唤醒大脑
        if self._brain:
            self._brain.awake()

        # 启动后台线程
        self._stop_event.clear()
        self._running = True
        self._stats["started_at"] = datetime.now(timezone.utc).isoformat()

        loop_configs = [
            ("feed", self._loop_feed, self.config.enable_feed),
            ("capture", self._loop_capture, self.config.enable_smart_capture),
            ("obsidian", self._loop_obsidian, self.config.enable_obsidian and self._obsidian is not None),
            ("evolution", self._loop_evolution, self.config.enable_self_evolution),
            ("nuro", self._loop_nuro, self.config.enable_nuro),
            ("feishu", self._loop_feishu, self.config.enable_feishu and self._feishu is not None),
        ]

        for name, target, enabled in loop_configs:
            if enabled:
                t = threading.Thread(target=target, name=f"orch-{name}", daemon=True)
                t.start()
                self._threads[name] = t
                logger.info("  ✓ %s 循环已启动", name)

        logger.info("Orchestrator 启动完成 — %d 个后台循环", len(self._threads))

    def stop(self):
        """优雅停止"""
        if not self._running:
            return

        logger.info("Orchestrator 停止中...")
        self._stop_event.set()

        # 等待线程结束
        for name, t in self._threads.items():
            t.join(timeout=5)
            if t.is_alive():
                logger.warning("  ⚠ %s 线程未在 5s 内停止", name)
            else:
                logger.info("  ✓ %s 循环已停止", name)

        # 大脑休眠
        if self._brain:
            self._brain.sleep()

        self._running = False
        self._threads.clear()
        logger.info("Orchestrator 已停止")

    def get_status(self) -> Dict[str, Any]:
        """获取全局状态"""
        status = {
            "running": self._running,
            "alpha_id": self._alpha_id,
            "stats": self._stats.copy(),
            "modules": {},
            "threads": {name: t.is_alive() for name, t in self._threads.items()},
        }

        # 各模块状态
        if self._feed:
            status["modules"]["feed"] = self._feed.get_stats()
        if self._capture:
            status["modules"]["capture"] = self._capture.get_stats()
        if self._obsidian:
            status["modules"]["obsidian"] = self._obsidian.get_stats()
        if self._feishu:
            status["modules"]["feishu"] = self._feishu.get_stats()
        if self._nuro:
            status["modules"]["nuro"] = self._nuro.get_stats()
        if self._evolution:
            status["modules"]["evolution"] = self._evolution.get_stats()
        if self._brain:
            status["modules"]["brain"] = {
                "state": self._brain.state.value,
                "message_count": self._brain._message_count,
            }

        return status

    # ── 便捷方法 ──

    def think(self, input_text: str = "") -> Dict[str, Any]:
        """通过大脑思考"""
        if not self._brain:
            return {"success": False, "message": "大脑未初始化"}
        return {"success": True, "result": self._brain.think()}

    def chat(self, user_input: str) -> str:
        """通过 NURO 聊天"""
        if self._nuro:
            return self._nuro.chat(user_input)
        if self._brain:
            result = self._brain.think()
            return str(result)
        return "系统未就绪"

    def capture_input(self, text: str, source: str = "manual"):
        """采集用户输入"""
        if self._capture:
            return self._capture.capture_user_input(text, source)
        return None

    def write_note(self, title: str, content: str, **kwargs) -> str:
        """写入 Obsidian 笔记"""
        if self._obsidian:
            return self._obsidian.write_note(title, content, **kwargs)
        return ""

    def learn_lesson(self, scenario: str, mistake: str, correction: str, lesson: str, **kwargs):
        """记录一条教训"""
        if self._evolution:
            return self._evolution.learn_from_correction(
                scenario=scenario,
                mistake=mistake,
                correction=correction,
                lesson=lesson,
                **kwargs,
            )
        return None

    def send_feishu(self, chat_id: str, text: str) -> bool:
        """发送飞书消息"""
        if self._feishu:
            return self._feishu.send_message(chat_id, text)
        return False

    def handle_feishu_webhook(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """处理飞书 Webhook"""
        if self._feishu:
            return self._feishu.handle_webhook(body)
        return {"code": 1, "msg": "飞书未启用"}

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
