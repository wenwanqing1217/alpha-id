# TERM: Container — 依赖注入容器（替代模块级全局单例，支持 SQLite/PostgreSQL 切换）
"""
依赖容器 — 替代模块级全局单例

提供：
- 单例管理（在 FastAPI lifespan 中初始化）
- lazy init + 线程安全
- 统一的存储后端切换点（SQLite / PostgreSQL）
- FastAPI 依赖注入支持（get_container）

存储后端选择：
- 默认：DATABASE_URL 环境变量决定（存在则用 Postgres，否则 SQLite）
- 测试：通过 storage setter 注入 mock
- 显式配置：os.environ["STORAGE_BACKEND"] = "sqlite" | "postgres"

依赖注入迁移（Phase 2）：
- 旧代码：Container.instance().xxx
- 新代码：在 FastAPI 路由中使用 Depends(get_container)
- 本文件保留 instance() 单例以兼容非 FastAPI 上下文（CLI、web.py）
"""

import logging
import threading
from typing import Any, Optional

from core.alpha_social import AlphaSocialManager
from core.memory_store import MemoryStore
from core.risk_engine import RiskAssessmentEngine
from core.settings import settings
from core.storage import StorageBackend
from core.storage_sqlite import SqliteStorage
from core.user_identity import UserIdentityManager

logger = logging.getLogger(__name__)

# 显式后端选择（可选，覆盖自动检测）
STORAGE_BACKEND = settings.storage_backend


def _create_default_storage() -> StorageBackend:
    """根据环境自动选择存储后端"""
    database_url = settings.database_url
    if database_url and database_url.startswith("postgresql"):
        try:
            from core.storage_postgres import PostgresStorage
            logger.info("Using PostgreSQL storage backend")
            return PostgresStorage()
        except ImportError:
            logger.warning("psycopg not installed, falling back to SQLite")
    elif STORAGE_BACKEND == "postgres":
        from core.storage_postgres import PostgresStorage
        return PostgresStorage()
    elif STORAGE_BACKEND == "sqlite" or not database_url:
        pass  # fall through to SQLite
    logger.info("Using SQLite storage backend")
    return SqliteStorage()


class Container:
    """应用级依赖容器"""

    _instance: Optional["Container"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._storage: Optional[StorageBackend] = None
        self._identity: Optional[UserIdentityManager] = None
        self._social: Optional[AlphaSocialManager] = None
        self._risk: Optional[RiskAssessmentEngine] = None
        self._memory: Optional[MemoryStore] = None
        self._credits: Optional[Any] = None  # CreditsManager（a-to-a 经济模型）
        # 新增模块（Phase 3）
        self._enricher: Optional[Any] = None
        self._feed: Optional[Any] = None
        self._capture: Optional[Any] = None
        self._obsidian: Optional[Any] = None
        self._feishu: Optional[Any] = None
        self._nuro: Optional[Any] = None
        self._evolution: Optional[Any] = None
        self._orchestrator: Optional[Any] = None
        # 新增模块（Phase 4）
        self._tool_orchestrator: Optional[Any] = None
        self._codex_api: Optional[Any] = None
        self._baidu_map: Optional[Any] = None

    @classmethod
    def instance(cls) -> "Container":
        """获取全局单例（线程安全）

        兼容旧代码。新代码应在 FastAPI 上下文中使用 Depends(get_container)。
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, container: "Container") -> None:
        """显式设置单例（用于测试注入或自定义初始化）"""
        with cls._lock:
            cls._instance = container

    @classmethod
    def reset_instance(cls) -> None:
        """清除单例（测试用）"""
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.close()
                except Exception:
                    pass
                cls._instance = None

    # ── 存储 ──

    @property
    def storage(self) -> StorageBackend:
        if self._storage is None:
            self._storage = _create_default_storage()
        return self._storage

    @storage.setter
    def storage(self, backend: StorageBackend):
        """允许测试注入 mock 或切换后端"""
        self._storage = backend
        # 重置所有已创建的 manager，使其下次用新存储重建
        self._identity = None
        self._social = None
        self._risk = None
        self._memory = None

    # ── Manager 实例（共享同一存储后端） ──

    @property
    def identity(self) -> UserIdentityManager:
        if self._identity is None:
            self._identity = UserIdentityManager(storage=self.storage)
        return self._identity

    @property
    def social(self) -> AlphaSocialManager:
        if self._social is None:
            # 注入用户存在性检查回调（H4: 社交功能验证目标用户存在）
            identity = self.identity
            self._social = AlphaSocialManager(
                storage=self.storage,
                user_exists_fn=identity.user_exists,
            )
            # 如果已经初始化了 feishu bridge（set_feishu_credentials 被调用过），直接注入
            if self._feishu is not None:
                self._social.set_feishu_bridge(self._feishu)
        else:
            # 延迟注入：feishu 在 social 之后才初始化的情况
            if self._feishu is not None and self._social._feishu_bridge is None:
                self._social.set_feishu_bridge(self._feishu)
        return self._social

    @property
    def risk(self) -> RiskAssessmentEngine:
        if self._risk is None:
            self._risk = RiskAssessmentEngine()
        return self._risk

    @property
    def memory(self) -> MemoryStore:
        if self._memory is None:
            # 用第一个注册的用户的 alpha_id 初始化；没有用户时用占位符
            try:
                users = self.storage.load("users") or {}
                first_id = next(iter(users), "Alpha-001")
            except Exception:
                first_id = "Alpha-001"
            self._memory = MemoryStore(first_id, storage=self.storage)
        return self._memory

    @property
    def credits(self):
        """积分钱包管理器（a-to-a 经济模型基础）

        复用 storage 后端 + social_manager（用于好友免费判断）。
        TERM: Credits — 积分系统（社交免费 + 陌生人付费）
        """
        if self._credits is None:
            from core.credits import CreditsManager
            self._credits = CreditsManager(
                storage=self.storage,
                social_manager=self.social,
            )
        return self._credits

    # ── 新增模块（Phase 3）──

    @property
    def enricher(self):
        """LLM 理解引擎"""
        if self._enricher is None:
            from alpha_id.enrichment.llm_enricher import LLMEnricher
            self._enricher = LLMEnricher()
        return self._enricher

    @property
    def feed(self):
        """资讯采集模块"""
        if self._feed is None:
            from alpha_id.feed import AgentFeed, FeedConfig
            self._feed = AgentFeed(FeedConfig())
        return self._feed

    @property
    def capture(self):
        """智能采集模块"""
        if self._capture is None:
            from alpha_id.smart_capture import SmartCapture
            self._capture = SmartCapture(
                llm_enricher=self.enricher,
                memory_store=self.memory,
            )
        return self._capture

    @property
    def obsidian(self):
        """Obsidian 桥接（需要手动设置路径后初始化）"""
        return self._obsidian

    def set_obsidian_vault(self, path: str):
        """设置 Obsidian 笔记库路径并初始化桥接"""
        from alpha_id.obsidian_bridge import ObsidianBridge
        self._obsidian = ObsidianBridge(path)
        # 同步让 Capture 也监控
        if self._capture:
            self._capture.watch_obsidian_vault(path)
        return self._obsidian

    @property
    def feishu(self):
        """飞书桥接"""
        return self._feishu

    def set_feishu_credentials(self, app_id: str, app_secret: str,
                                verification_token: str = "", encrypt_key: str = ""):
        """设置飞书凭证并初始化桥接；自动注入到已创建的 AlphaSocialManager"""
        from alpha_id.feishu_bridge import FeishuBridge
        self._feishu = FeishuBridge(
            app_id=app_id,
            app_secret=app_secret,
            verification_token=verification_token,
            encrypt_key=encrypt_key,
        )
        # 如果 social 已经创建了，同步注入 bridge（否则 social 的 getter 会在下一次访问时注入）
        if self._social is not None:
            self._social.set_feishu_bridge(self._feishu)
        return self._feishu

    @property
    def nuro(self):
        """NURO 桌宠桥接"""
        if self._nuro is None:
            from alpha_id.nuro_bridge import NUROBridge
            from fairy.fairy_brain import FairyBrain
            fairy = None
            try:
                fairy = FairyBrain()
                if not fairy.available:
                    fairy = None
            except Exception:
                pass
            self._nuro = NUROBridge(
                fairy_brain=fairy,
                memory_store=self.memory,
            )
        return self._nuro

    @property
    def evolution(self):
        """自进化引擎"""
        if self._evolution is None:
            from alpha_id.self_evolution import SelfEvolution
            self._evolution = SelfEvolution(
                memory_store=self.memory,
                llm_enricher=self.enricher,
            )
        return self._evolution

    @property
    def orchestrator(self):
        """总调度器"""
        if self._orchestrator is None:
            from alpha_id.orchestrator import MasterOrchestrator, OrchestratorConfig
            # 用第一个用户的 alpha_id
            try:
                users = self.storage.load("users") or {}
                first_id = next(iter(users), "Alpha-001")
            except Exception:
                first_id = "Alpha-001"
            config = OrchestratorConfig(alpha_id=first_id)
            self._orchestrator = MasterOrchestrator(config)
        return self._orchestrator

    # ── 新增模块（Phase 4）──

    @property
    def tool_orchestrator(self):
        """编程工具协同调度器"""
        if self._tool_orchestrator is None:
            from alpha_id.tool_orchestrator import ToolOrchestrator
            self._tool_orchestrator = ToolOrchestrator()
        return self._tool_orchestrator

    @property
    def codex_api(self):
        """Codex CLI HTTP 接口"""
        if self._codex_api is None:
            from alpha_id.codex_api import CodexAPIServer
            self._codex_api = CodexAPIServer()
        return self._codex_api

    @property
    def baidu_map(self):
        """百度地图 AI 技能客户端"""
        if self._baidu_map is None:
            from alpha_id.skills.baidu_ai_map import BaiduMapClient, BaiduMapConfig
            self._baidu_map = BaiduMapClient(BaiduMapConfig())
        return self._baidu_map

    # ── 生命周期 ──

    def reset(self):
        """测试用：清空所有单例"""
        self._storage = None
        self._identity = None
        self._social = None
        self._risk = None
        self._memory = None
        self._enricher = None
        self._feed = None
        self._capture = None
        self._obsidian = None
        self._feishu = None
        self._nuro = None
        self._evolution = None
        self._orchestrator = None
        self._tool_orchestrator = None
        self._codex_api = None
        self._baidu_map = None

    def close(self):
        """释放资源"""
        if hasattr(self._storage, "close"):
            self._storage.close()


# ── FastAPI 依赖注入 ──

try:
    from fastapi import Request

    def get_container(request: Request) -> Container:
        """FastAPI 依赖：从 app.state 获取 Container

        使用方式：
            @router.get("/xxx")
            def handler(container: Container = Depends(get_container)):
                ...

        优势：
        - 测试时可注入 mock container
        - 支持请求级别的容器隔离（多租户）
        - 消除对全局单例的直接依赖

        兼容回退：如果 app.state.container 未设置（例如 TestClient 未运行 lifespan），
        回退到全局单例 Container.instance()，保证非生产环境可用。
        """
        try:
            return request.app.state.container
        except AttributeError:
            return Container.instance()

    def _get_container_from_app(app) -> Optional[Container]:
        """从 FastAPI app 实例获取容器（非请求上下文使用）"""
        return getattr(app.state, "container", None)

except ImportError:
    # FastAPI 不可用时提供占位
    def get_container(request=None) -> Container:  # type: ignore[misc]
        """FastAPI 不可用，回退到单例"""
        return Container.instance()
