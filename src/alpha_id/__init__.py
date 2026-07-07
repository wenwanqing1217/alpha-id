"""
AID — Agent Identity Layer SDK

pip install alpha-id 入口包。

公开 API：
    Agent           — 一站式 AI 身份智能体
    Container       — 依赖容器
    DIDRegistry     — Agent DID 注册表（身份 + 签名 + 验证）
    AIDSigner       — 签名/验签 SDK
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
__version__ = "0.3.0"
