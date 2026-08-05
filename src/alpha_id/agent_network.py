"""AgentNetwork — 多 Agent 协作自治（P3-3）

Agent 间通过 DID 互相认证身份，技能调用链可追溯，多方 PoE 自动聚合。

用法：
    network = AgentNetwork(local_signer, registry=my_registry)
    network.register_peer(did=other_did, public_key=other_pk)

    # 调用其他 Agent 的技能（自动追踪调用链）
    result = network.call_skill("did:aid:peer...", "greet", {"name": "Alice"})

    # 聚合调用链 PoE
    chain = network.get_call_chain(result["poe_id"])
    print(chain.summary())
"""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from alpha_id.did_resolver import DIDResolver
from alpha_id.poe import PoEClient, PoEStore
from alpha_id.signer import AIDSigner
from alpha_id.skill_signer import SkillRegistry, SkillRuntime

logger = logging.getLogger(__name__)

# ── 数据模型 ──


@dataclass
class AgentPeer:
    """网络中的另一个 Agent 身份"""

    did: str
    public_key_hex: str = ""
    alpha_id: str = ""
    alias: str = ""
    trust_level: int = 50  # 0-100
    last_seen: float = 0.0
    skills_available: List[str] = field(default_factory=list)

    @property
    def public_key(self) -> bytes:
        return bytes.fromhex(self.public_key_hex)


@dataclass
class CallChainLink:
    """调用链中的一环"""

    poe_id: str
    skill_name: str
    executor_did: str
    author_did: str
    timestamp: float
    success: bool
    parent_poe_id: str = ""
    verified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CallChain:
    """完整的技能调用链"""

    links: List[CallChainLink] = field(default_factory=list)

    def add(self, link: CallChainLink):
        self.links.append(link)

    def last(self) -> Optional[CallChainLink]:
        return self.links[-1] if self.links else None

    def first(self) -> Optional[CallChainLink]:
        return self.links[0] if self.links else None

    def depth(self) -> int:
        return len(self.links)

    def all_successful(self) -> bool:
        return all(link.success for link in self.links)

    def all_verified(self) -> bool:
        return all(link.verified for link in self.links)

    def summary(self) -> str:
        if not self.links:
            return "(empty chain)"
        parts = []
        for i, link in enumerate(self.links):
            status = "✅" if link.success else "❌"
            verified = "✓" if link.verified else "?"
            executor = link.executor_did[-12:] if len(link.executor_did) > 12 else link.executor_did
            parts.append(f"  {i}: {status}[{verified}] {link.skill_name} by {executor}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "depth": self.depth(),
            "all_successful": self.all_successful(),
            "all_verified": self.all_verified(),
            "links": [link.to_dict() for link in self.links],
        }


# ── 网络核心 ──


class AgentNetwork:
    """多 Agent 协作网络"""

    def __init__(
        self,
        local_signer: AIDSigner,
        registry: Optional[SkillRegistry] = None,
        tracker=None,
        poe_store: Optional[PoEStore] = None,
        resolver: Optional[DIDResolver] = None,
    ):
        self._signer = local_signer
        self._registry = registry
        self._tracker = tracker
        self._poe_store = poe_store or PoEStore(storage_dir=".")  # default in-memory only
        self._resolver = resolver or DIDResolver()
        self._peers: Dict[str, AgentPeer] = {}  # did -> peer

    # ── 身份属性 ──

    @property
    def my_did(self) -> str:
        return self._signer.did

    # ── 对等节点管理 ──

    def register_peer(
        self, did: str, public_key_hex: str = "", alpha_id: str = "", alias: str = "", trust_level: int = 50
    ) -> AgentPeer:
        """注册/更新一个对等节点

        Args:
            did: 对等节点的 DID
            public_key_hex: 公钥 hex（可选，可从 DID 解析）
            alpha_id: Alpha-ID（可选）
            alias: 别名
            trust_level: 信任等级 0-100

        Returns:
            注册的 AgentPeer
        """
        # 验证 DID 格式
        if not did.startswith("did:aid:"):
            raise ValueError(f"无效 DID 格式: {did}")

        # 如果提供了公钥，验证匹配
        if public_key_hex:
            pk_bytes = bytes.fromhex(public_key_hex)
            if not DIDResolver.verify_did(did, pk_bytes):
                raise ValueError(f"公钥不匹配 DID: {did}")

        peer = AgentPeer(
            did=did,
            public_key_hex=public_key_hex,
            alpha_id=alpha_id,
            alias=alias,
            trust_level=trust_level,
            last_seen=time.time(),
        )
        self._peers[did] = peer
        return peer

    def get_peer(self, did: str) -> Optional[AgentPeer]:
        """获取已注册的对等节点"""
        return self._peers.get(did)

    def list_peers(self) -> List[AgentPeer]:
        """列出所有对等节点"""
        return list(self._peers.values())

    def remove_peer(self, did: str):
        """移除对等节点"""
        self._peers.pop(did, None)

    # ── DID 认证 ──

    def authenticate_peer(self, peer_did: str) -> bool:
        """验证对等节点的 DID 真实性

        使用 challenge-response 协议验证对方持有私钥：
        1. 生成随机 challenge
        2. 对方签名
        3. 用对方公钥验签

        这里简化实现：检查 DID 与公钥是否匹配。

        Args:
            peer_did: 对等节点 DID

        Returns:
            认证是否通过
        """
        peer = self._peers.get(peer_did)
        if peer is None:
            return False
        if not peer.public_key_hex:
            return False
        return DIDResolver.verify_did(peer_did, peer.public_key)

    # ── 技能调用 ──

    def call_skill(
        self, peer_did: str, skill_name: str, params: Dict[str, Any] = None, parent_poe_id: str = ""
    ) -> Dict[str, Any]:
        """调用对等节点的技能（自动追踪调用链）

        流程：
        1. 验证对等节点已认证
        2. 创建链式 PoE client
        3. 执行技能
        4. 生成 PoE

        Args:
            peer_did: 目标 Agent 的 DID
            skill_name: 技能名称
            params: 参数字典
            parent_poe_id: 父 PoE ID（链式调用时传递）

        Returns:
            {"success": bool, "result": str, "poe_id": str, "poe": ...}
        """
        if self._registry is None:
            return {"success": False, "error": "未配置技能注册表"}

        peer = self._peers.get(peer_did)
        if peer is None:
            return {"success": False, "error": f"未知对等节点: {peer_did}"}

        if not self.authenticate_peer(peer_did):
            return {"success": False, "error": f"对等节点未认证: {peer_did}"}

        params = params or {}

        # 创建链式 PoE client
        poe_client = PoEClient(
            self._signer,
            store=self._poe_store,
            parent_poe_id=parent_poe_id,
        )

        # 执行技能
        runtime = SkillRuntime(
            self._registry,
            tracker=self._tracker,
            poe_client=poe_client,
        )
        params_json = json.dumps(params, ensure_ascii=False)
        result = runtime.execute(
            skill_name,
            params_json,
            executor_did=self._signer.did,
        )

        # 获取刚生成的 PoE（最新的那条）
        poe_id = ""
        if parent_poe_id:
            # 查找子 PoE
            for poe in self._poe_store.list_all(limit=10):
                if poe.parent_poe_id == parent_poe_id and poe.executor_did == self._signer.did:
                    poe_id = poe.poe_id
                    break
        else:
            # 取最新的 PoE
            all_poes = self._poe_store.list_all(limit=5)
            if all_poes:
                poe_id = all_poes[0].poe_id

        # 更新信任等级
        is_success = not result.startswith("[错误]")
        if is_success:
            peer.trust_level = min(100, peer.trust_level + 1)
        else:
            peer.trust_level = max(0, peer.trust_level - 5)
        peer.last_seen = time.time()

        return {
            "success": is_success,
            "result": result,
            "poe_id": poe_id,
            "peer_did": peer_did,
            "skill_name": skill_name,
        }

    # ── 调用链追踪 ──

    def get_call_chain(self, poe_id: str) -> CallChain:
        """从 PoE ID 追溯完整的调用链

        递归地追踪 parent_poe_id，构建完整的调用链。
        使用 visited 集合检测循环引用，防止无限循环。

        Args:
            poe_id: 起始 PoE ID

        Returns:
            完整的调用链
        """
        chain = CallChain()
        current_id = poe_id
        visited = set()  # 循环检测：记录已访问的 poe_id

        while current_id:
            # 循环检测：如果当前 ID 已访问过，说明存在环，终止追踪
            if current_id in visited:
                logger.warning(
                    "调用链检测到循环引用: poe_id=%s 已访问过，停止追踪",
                    current_id,
                )
                break
            visited.add(current_id)

            poe = self._poe_store.get(current_id)
            if poe is None:
                break

            # 验证 PoE 签名
            try:
                peer = self._peers.get(poe.executor_did)
                verified = False
                if peer and peer.public_key_hex:
                    verified = poe.verify(peer.public_key)
            except Exception:
                verified = False

            link = CallChainLink(
                poe_id=poe.poe_id,
                skill_name=poe.skill_name,
                executor_did=poe.executor_did,
                author_did=poe.author_did,
                timestamp=poe.timestamp,
                success=poe.success,
                parent_poe_id=poe.parent_poe_id,
                verified=verified,
            )
            chain.add(link)
            current_id = poe.parent_poe_id if poe.parent_poe_id else None

        return chain

    # ── PoE 聚合 ──

    def aggregate_poes(self, poe_ids: List[str]) -> Dict[str, Any]:
        """聚合多个 PoE 记录

        Args:
            poe_ids: 要聚合的 PoE ID 列表

        Returns:
            {"total": int, "successful": int, "failed": int,
             "verified": int, "skills": [str], "executors": [str]}
        """
        total = 0
        successful = 0
        verified_count = 0
        skills = set()
        executors = set()
        errors = []

        for poe_id in poe_ids:
            poe = self._poe_store.get(poe_id)
            if poe is None:
                errors.append(f"PoE 未找到: {poe_id}")
                continue
            total += 1
            if poe.success:
                successful += 1
            skills.add(poe.skill_name)
            executors.add(poe.executor_did)

            # 验证签名
            peer = self._peers.get(poe.executor_did)
            if peer and peer.public_key_hex:
                try:
                    if poe.verify(peer.public_key):
                        verified_count += 1
                except Exception:
                    pass

        return {
            "total": total,
            "successful": successful,
            "failed": total - successful,
            "verified": verified_count,
            "skills": sorted(skills),
            "executors": sorted(executors),
            "errors": errors,
        }

    # ── 发现 ──

    def discover_peers_from_repo(self, repo_paths: List[str]) -> List[AgentPeer]:
        """从技能仓库发现对等节点

        扫描仓库中的 repository.json，提取作者 DID 并注册。

        Args:
            repo_paths: 仓库路径列表

        Returns:
            新发现的对等节点
        """
        from alpha_id.skill_repository import SkillRepository

        repo_client = SkillRepository(resolver=self._resolver)
        discovered = []

        for rp in repo_paths:
            meta = repo_client.get_repo_meta(rp)
            if meta and meta.author_did:
                if meta.author_did not in self._peers:
                    peer = self.register_peer(
                        did=meta.author_did,
                        alias=meta.name,
                        trust_level=30,  # 初始较低信任
                    )
                    discovered.append(peer)

        return discovered

    # ── 持久化 ──

    def save_peers(self, path: str):
        """持久化对等节点列表"""
        data = {did: asdict(peer) for did, peer in self._peers.items()}
        import json

        Path(path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_peers(self, path: str):
        """从文件加载对等节点列表"""
        import json

        p = Path(path)
        if not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        self._peers.clear()
        for did, d in data.items():
            self._peers[did] = AgentPeer(**d)
