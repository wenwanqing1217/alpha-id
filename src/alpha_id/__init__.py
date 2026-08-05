"""
AID — Agent Identity Layer SDK

pip install alpha-id 入口包。

公开 API：
    Agent           — 一站式 AI 身份智能体
    Container       — 依赖容器
    DIDRegistry     — Agent DID 注册表（身份 + 签名 + 验证）
    AIDSigner       — 签名/验签 SDK

    # Phase 3: 新增模块
    AgentFeed       — 资讯采集（GitHub/HN/ArXiv/RSS）
    SmartCapture    — 智能采集（侦探模式：发现矛盾/卡住/偏离）
    ObsidianBridge  — Obsidian 双向同步
    FeishuBridge    — 飞书集成（消息/工作上下文）
    NUROBridge      — 桌宠连接（本地小模型 + 云端 LLM）
    SelfEvolution   — 自进化引擎（教训/偏好审视/知识沉淀）
    MasterOrchestrator — 总调度器（串联所有模块）

    # Phase 4: 新增模块
    ToolOrchestrator — 编程工具协同调度（串行/并行 + 线程池）
    CodexAPIServer   — Codex CLI HTTP 接口（atomcode/codex 后端）
    BaiduMapClient   — 百度地图 AI 技能（地点/路线/天气/地理编码）
"""

from .agent import Agent
from .agent_network import AgentNetwork, AgentPeer, CallChain, CallChainLink
from .container import Container
from .did import DIDDocument, DIDRegistry
from .did_resolver import DIDResolver
from .poe import PoEClient, PoEStore, ProofOfExecution
from .signer import AIDSigner
from .skill_repository import RepositoryMeta, RepositorySkill, SkillRepository
from .skill_signer import (
    AttributionRecord,
    SkillAttributionTracker,
    SkillPackage,
    SkillRegistry,
    SkillRuntime,
    sign_skill,
    verify_skill,
)

# ── Phase 3: 新增模块（延迟导入，优雅降级）──

try:
    from .feed import AgentFeed, FeedConfig, FeedItem  # noqa: F401
    HAS_FEED = True
except ImportError:
    HAS_FEED = False

try:
    from .smart_capture import Observation, SmartCapture, UserContext  # noqa: F401
    HAS_SMART_CAPTURE = True
except ImportError:
    HAS_SMART_CAPTURE = False

try:
    from .obsidian_bridge import NoteEvent, ObsidianBridge  # noqa: F401
    HAS_OBSIDIAN = True
except ImportError:
    HAS_OBSIDIAN = False

try:
    from .feishu_bridge import FeishuBridge, FeishuMessage  # noqa: F401
    HAS_FEISHU = True
except ImportError:
    HAS_FEISHU = False

try:
    from .nuro_bridge import NUROBridge, NUROEvent  # noqa: F401
    HAS_NURO = True
except ImportError:
    HAS_NURO = False

try:
    from .self_evolution import Lesson, PreferenceAudit, SelfEvolution  # noqa: F401
    HAS_EVOLUTION = True
except ImportError:
    HAS_EVOLUTION = False

try:
    from .orchestrator import MasterOrchestrator, OrchestratorConfig  # noqa: F401
    HAS_ORCHESTRATOR = True
except ImportError:
    HAS_ORCHESTRATOR = False

try:
    from .tool_orchestrator import Task, TaskConfig, ToolOrchestrator  # noqa: F401
    HAS_TOOL_ORCHESTRATOR = True
except ImportError:
    HAS_TOOL_ORCHESTRATOR = False

try:
    from .codex_api import CodexAPIServer  # noqa: F401
    HAS_CODEX_API = True
except ImportError:
    HAS_CODEX_API = False

try:
    from .skills.baidu_ai_map import BaiduMapClient, BaiduMapConfig  # noqa: F401
    HAS_BAIDU_MAP = True
except ImportError:
    HAS_BAIDU_MAP = False

# ── 公开 API ──

__all__ = [
    "Agent",
    "Container",
    "DIDRegistry",
    "DIDDocument",
    "AIDSigner",
    "ProofOfExecution",
    "PoEStore",
    "PoEClient",
    "SkillPackage",
    "SkillRegistry",
    "SkillRuntime",
    "SkillAttributionTracker",
    "AttributionRecord",
    "sign_skill",
    "verify_skill",
    "DIDResolver",
    "SkillRepository",
    "RepositoryMeta",
    "RepositorySkill",
    "AgentNetwork",
    "AgentPeer",
    "CallChain",
    "CallChainLink",
]

# 动态添加新模块到 __all__
if HAS_FEED:
    __all__.extend(["AgentFeed", "FeedConfig", "FeedItem"])
if HAS_SMART_CAPTURE:
    __all__.extend(["SmartCapture", "Observation", "UserContext"])
if HAS_OBSIDIAN:
    __all__.extend(["ObsidianBridge", "NoteEvent"])
if HAS_FEISHU:
    __all__.extend(["FeishuBridge", "FeishuMessage"])
if HAS_NURO:
    __all__.extend(["NUROBridge", "NUROEvent"])
if HAS_EVOLUTION:
    __all__.extend(["SelfEvolution", "Lesson", "PreferenceAudit"])
if HAS_ORCHESTRATOR:
    __all__.extend(["MasterOrchestrator", "OrchestratorConfig"])
if HAS_TOOL_ORCHESTRATOR:
    __all__.extend(["ToolOrchestrator", "TaskConfig", "Task"])
if HAS_CODEX_API:
    __all__.extend(["CodexAPIServer"])
if HAS_BAIDU_MAP:
    __all__.extend(["BaiduMapClient", "BaiduMapConfig"])

__version__ = "0.4.0"
