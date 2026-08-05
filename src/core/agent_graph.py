"""AgentGraph — 多 Agent 网络拓扑与路由

TERM: AgentGraph — A2A 网络拓扑（运行时计算 + 持久化混合）

设计理念：
  AgentGraph 是"地基"，负责 findskill（找最优工具路径）。
  总助通过 AgentGraph 调度任务闭环。

核心能力：
  1. register_agent(agent_info) — 注册 agent 节点
  2. find_skill(skill_name) — 查找哪个 agent 提供某个 skill
  3. find_best_agent(skill_name, prefer="free") — 找最优 agent（免费优先）
  4. record_call(caller, target, skill, success) — 记录调用边
  5. get_topology() — 返回 nodes+edges 供可视化

节点类型：
  - "core"    内部核心 agent（AgentLoop/TwinBrain）
  - "tool"    工具类 agent（文案/视频/抖音/短剧/地图/feed）
  - "external" 外部 agent（用户 DIY 接入）
  - "feed"    资讯类 agent（GitHub/HN/ArXiv/RSS/WorldMonitor）

选路策略（prefer 参数）：
  - "free"   优先免费 agent（is_free=True）
  - "fast"   优先响应快的 agent（按历史 latency）
  - "reliable" 优先成功率高的 agent（按历史 success_rate）
  - "any"    任意可用
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AgentNode:
    """Agent 节点"""
    agent_id: str            # 唯一标识（did 或 service_id）
    name: str                # 显示名
    agent_type: str          # core / tool / external / feed / user
    endpoint: str            # HTTP 端点（如 http://localhost:8081）
    skills: List[str] = field(default_factory=list)  # 提供的 skill 列表
    is_free: bool = True     # 是否免费（免费 API 优先）
    is_online: bool = True   # 是否在线
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    # ── 用户 a to a 字段 ──
    owner_alpha_id: str = ""           # 归属用户（空=平台基建）
    status: str = "approved"           # pending / approved / delisted
    price_credits: int = 0             # 调用一次扣多少积分（0=免费）
    api_key: str = ""                  # 简化接入的 API Key（用户可选，替代 Ed25519）
    category: str = ""                 # 市场分类（如"视频"/"文案"/"资讯"）
    rating: float = 0.0                # 评分（0-5，由调用者评价）
    total_calls: int = 0               # 总调用次数


@dataclass
class CallEdge:
    """调用边（谁调用过谁的什么 skill）"""
    caller: str              # 调用方 agent_id
    target: str              # 目标 agent_id
    skill: str               # 调用的 skill
    success: bool = True     # 是否成功
    latency_ms: float = 0    # 响应延迟
    timestamp: float = field(default_factory=time.time)


class AgentGraph:
    """Agent 网络拓扑 — 运行时计算 + 内存持久化

    与现有 /api/v1/a2a/graph 端点的关系：
      - 现有端点从 registry + audit log 现算 nodes+edges
      - AgentGraph 在内存维护完整拓扑，支持 find_skill 等图查询
      - get_topology() 返回相同格式，可替换现有端点
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, AgentNode] = {}
        self._edges: List[CallEdge] = []
        # 索引：skill_name → [agent_id, ...] 提供该 skill 的 agent 列表
        self._skill_index: Dict[str, List[str]] = defaultdict(list)
        # 统计：agent_id → {success_count, fail_count, total_latency, call_count}
        self._stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "success_count": 0,
            "fail_count": 0,
            "total_latency_ms": 0.0,
            "call_count": 0,
        })
        # 基建层最优自替换：skill_name → 当前最优 agent_id
        self._preferred: Dict[str, str] = {}
        # 外部 skill 市场源（OpenRouter / Gorilla / 自建注册中心等）
        # name → {base_url, skill_map: {skill: [agent_meta, ...]}, agent_template}
        self._external_sources: Dict[str, Dict[str, Any]] = {}

    # ── 外部 skill 市场（OpenRouter / Gorilla / 自建注册中心）────────────────

    def register_external_source(
        self,
        name: str,
        base_url: str,
        skill_map: Dict[str, List[Dict[str, Any]]],
        agent_template: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """登记一个外部 skill 市场源。

        Args:
            name: 源名称（如 "openrouter" / "gorilla"）
            base_url: 源根地址（用于后续真实拉取，预留）
            skill_map: {skill_name: [{id, name, endpoint, is_free, price_credits, ...}, ...]}
            agent_template: 可选的默认字段模板，合并进每个 agent 元信息
        """
        self._external_sources[name] = {
            "base_url": base_url,
            "skill_map": skill_map,
            "agent_template": agent_template or {},
            "synced": False,
        }
        logger.info("AgentGraph 外部市场登记: %s (skills=%d)", name, len(skill_map))
        return True

    def sync_external_skills(self, source_name: Optional[str] = None) -> int:
        """把外部市场登记的 agent 以 external 类型注册进图（幂等）。

        Args:
            source_name: 只同步指定源；None 表示同步全部

        Returns:
            本次新增的 agent 数量（已存在的跳过）
        """
        added = 0
        for name, src in self._external_sources.items():
            if source_name and name != source_name:
                continue
            for skill, metas in src["skill_map"].items():
                for meta in metas:
                    agent_id = f"ext-{name}-{meta.get('id', skill)}"
                    if agent_id in self._nodes:
                        continue
                    tmpl = dict(src["agent_template"])
                    tmpl.update(meta)
                    node = AgentNode(
                        agent_id=agent_id,
                        name=tmpl.get("name", agent_id),
                        agent_type="external",
                        endpoint=tmpl.get("endpoint", ""),
                        skills=[skill],
                        is_free=bool(tmpl.get("is_free", True)),
                        is_online=bool(tmpl.get("is_online", True)),
                        status="approved",
                        price_credits=int(tmpl.get("price_credits", 0)),
                        description=tmpl.get("description", ""),
                        metadata={"source": name, "external": True},
                    )
                    self.register_agent(node)
                    added += 1
            src["synced"] = True
        return added

    def list_external_sources(self) -> List[Dict[str, Any]]:
        """列出所有外部市场源及同步状态"""
        return [
            {"name": n, "base_url": s["base_url"], "skills": len(s["skill_map"]), "synced": s["synced"]}
            for n, s in self._external_sources.items()
        ]

    def _count_external_agents(self) -> int:
        """统计已注册的外部 agent 数量"""
        return sum(1 for n in self._nodes.values() if n.metadata.get("external"))

    # ── 节点管理 ──────────────────────────────────────────────

    def register_agent(self, node: AgentNode) -> bool:
        """注册 agent 节点。已存在则更新。"""
        self._nodes[node.agent_id] = node
        # 更新 skill 索引
        for skill in node.skills:
            if node.agent_id not in self._skill_index[skill]:
                self._skill_index[skill].append(node.agent_id)
        logger.info(
            "AgentGraph 注册: %s (%s) skills=%s free=%s",
            node.name, node.agent_type, node.skills, node.is_free,
        )
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        """注销 agent 节点"""
        node = self._nodes.pop(agent_id, None)
        if not node:
            return False
        # 清理 skill 索引
        for skill in node.skills:
            if agent_id in self._skill_index[skill]:
                self._skill_index[skill].remove(agent_id)
                if not self._skill_index[skill]:
                    del self._skill_index[skill]
        logger.info("AgentGraph 注销: %s", agent_id)
        return True

    def get_agent(self, agent_id: str) -> Optional[AgentNode]:
        return self._nodes.get(agent_id)

    def list_agents(
        self,
        agent_type: Optional[str] = None,
        owner_alpha_id: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        include_unlisted: bool = False,
        viewer_alpha_id: str = "",
    ) -> List[AgentNode]:
        """列出 agent，支持过滤

        Args:
            agent_type: 按类型过滤（core/tool/external/feed）
            owner_alpha_id: 按 owner 过滤
            category: 按分类过滤
            status: 按状态过滤
            include_unlisted: 是否包含未上架（pending/submitted/delisted）
            viewer_alpha_id: 查看者的 alpha_id（用于状态可见性：
                非 approved 状态的 agent 仅 owner 自己能看见）
        """
        result = []
        for n in self._nodes.values():
            if agent_type and n.agent_type != agent_type:
                continue
            if owner_alpha_id is not None and n.owner_alpha_id != owner_alpha_id:
                continue
            if category and n.category != category:
                continue
            if status and n.status != status:
                continue
            # 状态可见性：非 approved 的 agent 仅 owner 自己 + 管理员（include_unlisted）可见
            if n.status != "approved" and not include_unlisted:
                if not viewer_alpha_id or n.owner_alpha_id != viewer_alpha_id:
                    continue
            result.append(n)
        return result

    def search_agents(
        self,
        query: str = "",
        category: Optional[str] = None,
        viewer_alpha_id: str = "",
        include_unlisted: bool = False,
        limit: int = 50,
    ) -> List[AgentNode]:
        """搜索 agent（按名称/描述/skills 匹配，市场页用）"""
        q = query.lower().strip()
        result = []
        for n in self._nodes.values():
            # 状态可见性
            if n.status != "approved" and not include_unlisted:
                if not viewer_alpha_id or n.owner_alpha_id != viewer_alpha_id:
                    continue
            if category and n.category != category:
                continue
            if q:
                # 名称/描述/skills 任一匹配
                hay = (
                    n.name.lower() + " " +
                    n.description.lower() + " " +
                    " ".join(n.skills).lower() + " " +
                    n.category.lower()
                )
                if q not in hay:
                    continue
            result.append(n)
            if len(result) >= limit:
                break
        # 排序：评分高的在前
        result.sort(key=lambda x: (-x.rating, -x.total_calls))
        return result

    def heartbeat(self, agent_id: str) -> bool:
        """更新 agent 心跳（在线状态）"""
        node = self._nodes.get(agent_id)
        if not node:
            return False
        node.last_heartbeat = time.time()
        node.is_online = True
        return True

    # ── 边管理 ────────────────────────────────────────────────

    def record_call(
        self,
        caller: str,
        target: str,
        skill: str,
        success: bool = True,
        latency_ms: float = 0,
    ) -> None:
        """记录一次调用（用于构建拓扑边 + 统计）"""
        edge = CallEdge(
            caller=caller,
            target=target,
            skill=skill,
            success=success,
            latency_ms=latency_ms,
        )
        self._edges.append(edge)
        # 限制边历史长度（保留最近 10000 条）
        if len(self._edges) > 10000:
            self._edges = self._edges[-5000:]

        # 更新统计
        stats = self._stats[target]
        stats["call_count"] += 1
        if success:
            stats["success_count"] += 1
        else:
            stats["fail_count"] += 1
        stats["total_latency_ms"] += latency_ms

    # ── 图查询：find_skill / find_best_agent ─────────────────

    def find_skill(self, skill_name: str) -> List[AgentNode]:
        """查找提供某个 skill 的所有 agent"""
        agent_ids = self._skill_index.get(skill_name, [])
        return [self._nodes[aid] for aid in agent_ids if aid in self._nodes]

    def find_best_agent(
        self,
        skill_name: str,
        prefer: str = "free",
        exclude: Optional[Set[str]] = None,
        owner_alpha_id: str = "",
        include_pending: bool = False,
    ) -> Optional[AgentNode]:
        """找到提供某 skill 的最优 agent

        Args:
            skill_name: 要找的 skill
            prefer: 选路策略
                "free"      优先免费 agent（is_free=True）
                "fast"      优先响应快的（按历史 avg_latency）
                "reliable"  优先成功率高的（按历史 success_rate）
                "owned"     优先 owner_alpha_id 自己的 agent
                "any"       任意可用
            exclude: 排除的 agent_id 集合（避免环路）
            owner_alpha_id: 调用方的 alpha_id（用于 owned 策略 + 状态可见性）
            include_pending: 是否包含 pending/submitted 状态的 agent（管理员用）

        Returns:
            最优 agent 节点，或 None（无可用）

        状态可见性：
            - approved   所有人可见
            - pending    仅 owner 自己可见（草稿）
            - submitted  仅 owner 自己可见 + 管理员（待审核）
            - delisted   不可见（已下架，除非 include_pending=True）
        """
        candidates = self.find_skill(skill_name)
        if not candidates:
            return None

        exclude = exclude or set()
        # 过滤：在线 + 状态可见性
        filtered = []
        for c in candidates:
            if c.agent_id in exclude:
                continue
            if not c.is_online:
                continue
            if c.status == "delisted":
                if not include_pending:
                    continue
            elif c.status in ("pending", "submitted"):
                # pending/submitted 只对 owner 自己可见（管理员通过 include_pending=True 查看）
                if not include_pending:
                    if not owner_alpha_id or c.owner_alpha_id != owner_alpha_id:
                        continue
            filtered.append(c)

        if not filtered:
            return None
        candidates = filtered

        # 基建层最优自替换：有 preferred 且它仍在候选池里，优先用它（除非调用方显式要 owned 策略）
        pref_id = self._preferred.get(skill_name, "")
        if pref_id and prefer != "owned":
            pref_node = next((c for c in candidates if c.agent_id == pref_id), None)
            if pref_node is not None:
                return pref_node

        if prefer == "owned" and owner_alpha_id:
            # 优先自己的 agent，其次好友的，最后市场的
            owned = [c for c in candidates if c.owner_alpha_id == owner_alpha_id]
            if owned:
                return owned[0]
            # 没有自己的，回退到 free 策略
            prefer = "free"

        # ── 判断好友关系（用于 owned 策略和 free 策略排序） ──
        friends_set = set()
        if owner_alpha_id:
            try:
                # 尝试从 container 获取 social manager；取不到就跳过
                _cls = None
                for _mod in ("alpha_id.container", "core.alpha_social"):
                    try:
                        _imported = __import__(_mod, fromlist=["Container", "AlphaSocialManager"])
                        if _mod == "alpha_id.container" and hasattr(_imported, "Container"):
                            _cls = _imported.Container
                        if _mod == "core.alpha_social" and hasattr(_imported, "AlphaSocialManager"):
                            pass
                    except Exception:
                        pass
                if _cls is not None:
                    try:
                        c = _cls.instance()
                        if hasattr(c, "_social") and c._social is not None:
                            friends_set = set(c._social.get_friends(owner_alpha_id))
                    except Exception:
                        pass
            except Exception:
                friends_set = set()

        if prefer == "owned" and owner_alpha_id:
            owned = [c for c in candidates if c.owner_alpha_id == owner_alpha_id]
            if owned:
                # 自己的里：免费优先，其次评分
                owned_free = [c for c in owned if c.is_free or c.price_credits == 0]
                if owned_free:
                    owned_free.sort(key=lambda c: (-c.rating, -self._success_rate(c.agent_id)))
                    return owned_free[0]
                owned.sort(key=lambda c: (c.price_credits, -c.rating))
                return owned[0]
            prefer = "free"  # 回退

        if prefer == "free":
            # TERM: 调度层免费优先 — 基建 agent 置顶 → 自己的免费 → 好友免费 → 其他免费；付费只在免费不可用时兜底
            free = [c for c in candidates if c.is_free or c.price_credits == 0]
            paid = [c for c in candidates if not (c.is_free or c.price_credits == 0)]
            if free:
                candidates = free
                # 免费内部排序：基建 > 自己 > 好友 > 其他，每段再按评分+成功率
                def _sort_key(c: AgentNode):
                    tier = 3  # 默认 3=其他免费
                    if not c.owner_alpha_id:
                        tier = 0  # 0=平台基建
                    elif owner_alpha_id and c.owner_alpha_id == owner_alpha_id:
                        tier = 1  # 1=自己的
                    elif owner_alpha_id and c.owner_alpha_id in friends_set:
                        tier = 2  # 2=好友的
                    return (tier, -c.rating, -self._success_rate(c.agent_id))
                candidates.sort(key=_sort_key)
            else:
                # 没免费的，付费按价格低→高，其次评分
                paid.sort(key=lambda c: (c.price_credits, -c.rating, -self._success_rate(c.agent_id)))
                candidates = paid
        elif prefer == "fast":
            candidates.sort(key=lambda c: self._avg_latency(c.agent_id))
        elif prefer == "reliable":
            candidates.sort(key=lambda c: (-self._success_rate(c.agent_id), -c.rating))
        # "any" 不排序

        return candidates[0]

    def find_path(
        self,
        caller: str,
        target_skill: str,
        max_depth: int = 3,
    ) -> Optional[List[AgentNode]]:
        """BFS 找到从 caller 到目标 skill 的最短路径

        用于多跳调用（agent A 调用 agent B 的 skill，B 再调用 C 的 skill）。
        目前大多数场景 max_depth=1 即可（直接找到提供 skill 的 agent）。

        Returns:
            路径节点列表（不含 caller），或 None
        """
        if max_depth < 1:
            return None

        # 第一跳：直接找提供 target_skill 的 agent
        visited = {caller}
        first_hop = self.find_skill(target_skill)
        for node in first_hop:
            if node.is_online and node.agent_id not in visited:
                return [node]

        if max_depth == 1:
            return None

        # 多跳：BFS（暂不实现复杂多跳，绝大多数场景一跳足够）
        # TODO: 如果需要 agent 间协作（A→B→C），再实现多跳 BFS
        return None

    # ── 统计与拓扑 ────────────────────────────────────────────

    def _success_rate(self, agent_id: str) -> float:
        stats = self._stats.get(agent_id, {})
        total = stats.get("call_count", 0)
        if total == 0:
            return 1.0  # 无历史记录默认满分（给新 agent 机会）
        return stats.get("success_count", 0) / total

    def _avg_latency(self, agent_id: str) -> float:
        stats = self._stats.get(agent_id, {})
        count = stats.get("call_count", 0)
        if count == 0:
            return 0.0
        return stats.get("total_latency_ms", 0) / count

    def get_agent_stats(self, agent_id: str) -> Dict[str, Any]:
        """获取 agent 调用统计"""
        stats = dict(self._stats.get(agent_id, {}))
        stats["success_rate"] = self._success_rate(agent_id)
        stats["avg_latency_ms"] = self._avg_latency(agent_id)
        return stats

    # ── 基建层最优自替换 ──────────────────────────────────────

    def benchmark_skill(
        self,
        skill_name: str,
        params: Optional[Dict[str, Any]] = None,
        probe: Optional[Callable[[AgentNode, Dict[str, Any]], Tuple[bool, float]]] = None,
        max_samples: int = 5,
    ) -> List[Dict[str, Any]]:
        """对提供某 skill 的所有基建 agent 做基准测试（返回评分排名）

        Args:
            skill_name: 要对比的 skill
            params: 调用参数（为 None 时只做统计评分，不真实调用）
            probe: 可选的真实调用探针函数，输入 (node, params) → (success, latency_ms)
                   无 probe 时只按历史统计评分
            max_samples: 最多取几个候选做对比（限流保护）

        Returns:
            评分排名列表，每元素 {agent_id, score, success_rate, avg_latency, is_free, probed_success, probed_latency}
            score 越高越好（免费加权 + 成功率加权 + 延迟负加权）
        """
        candidates = [
            c for c in self.find_skill(skill_name)
            if c.is_online and c.status == "approved" and not c.owner_alpha_id
            # 只看基建 agent（owner 空 = 平台内置最优池）
        ]
        if not candidates:
            return []

        # 只取 max_samples 个做对比（按当前评分先过滤出最可能最优的）
        candidates.sort(key=lambda c: (
            0 if (c.is_free or c.price_credits == 0) else 1,
            -self._success_rate(c.agent_id),
            self._avg_latency(c.agent_id),
        ))
        candidates = candidates[:max_samples]

        results = []
        for c in candidates:
            sr = self._success_rate(c.agent_id)
            lat = self._avg_latency(c.agent_id)
            free_tag = 1.0 if (c.is_free or c.price_credits == 0) else 0.0

            # 基础评分（0-100）：免费 +40，成功率 ×40，延迟负向 20
            latency_bonus = 20.0 if lat <= 0 else max(0.0, 20.0 - lat / 100.0)  # 0ms=20分，每慢100ms扣1分
            score = free_tag * 40 + sr * 40 + latency_bonus

            probed_success = None
            probed_latency = None
            # 如果有 probe，跑真实调用
            if probe and params is not None:
                try:
                    probed_success, probed_latency = probe(c, params)
                    # 真实结果二次评分
                    if probed_success:
                        score += 20  # 真调成功 +20
                        score = min(100, score)
                        real_lat_bonus = max(0.0, 20.0 - probed_latency / 100.0)
                        score = min(100, score + real_lat_bonus)
                    else:
                        score -= 30
                        score = max(0, score)
                except Exception as e:
                    logger.debug("probe 失败 [%s]: %s", c.agent_id, e)
                    score -= 20
                    score = max(0, score)

            results.append({
                "agent_id": c.agent_id,
                "name": c.name,
                "score": round(score, 2),
                "success_rate": round(sr, 3),
                "avg_latency_ms": round(lat, 1),
                "is_free": free_tag > 0,
                "probed_success": probed_success,
                "probed_latency_ms": probed_latency,
                "calls": self._stats.get(c.agent_id, {}).get("call_count", 0),
            })

        results.sort(key=lambda x: -x["score"])
        return results

    def swap_to_best(self, skill_name: str, min_score_gain: float = 5.0) -> Dict[str, Any]:
        """对比当前在用 vs 候选，若新最优明显更好则自动替换 preferred_agent 标签

        用法：OrchestratorEngine 的定期最优自替换循环调用此方法，
        平台基建层保证"根据当前最优做切换"，省去人工一直找。

        Args:
            min_score_gain: 至少多多少分才替换（防止频繁抖动）
        Returns:
            {"action": "swapped"|"kept"|"no_candidates", "prev": ..., "new": ...}
        """
        rankings = self.benchmark_skill(skill_name)
        if not rankings:
            return {"action": "no_candidates", "skill": skill_name}

        # 当前"在用" = 之前的最优（preferred 存在就用，否则是 find_best_agent 默认选的）
        prev_id = self._preferred.get(skill_name, "")
        best = rankings[0]

        if prev_id == best["agent_id"]:
            return {
                "action": "kept",
                "skill": skill_name,
                "preferred": best["agent_id"],
                "score": best["score"],
                "reason": "仍然最优",
            }

        prev_score = 0.0
        for r in rankings:
            if r["agent_id"] == prev_id:
                prev_score = r["score"]
                break

        # 如果 prev_id 压根不在候选池里，直接换
        if prev_id and best["score"] - prev_score < min_score_gain:
            return {
                "action": "kept",
                "skill": skill_name,
                "preferred": prev_id,
                "prev_score": prev_score,
                "best_score": best["score"],
                "reason": f"分差 {best['score'] - prev_score:.1f} < {min_score_gain}，不抖动",
            }

        # 执行替换
        self._preferred[skill_name] = best["agent_id"]
        logger.info(
            "[基建自替换] skill=%s: %s(%.1f) → %s(%.1f) ▲%.1f",
            skill_name, prev_id or "(空)", prev_score,
            best["agent_id"], best["score"], best["score"] - prev_score,
        )
        return {
            "action": "swapped",
            "skill": skill_name,
            "prev": prev_id,
            "prev_score": prev_score,
            "new": best["agent_id"],
            "new_score": best["score"],
            "gain": round(best["score"] - prev_score, 1),
            "rankings": rankings[:3],
        }

    def run_optimal_swap_pass(self, skills: Optional[List[str]] = None, min_gain: float = 5.0) -> List[Dict[str, Any]]:
        """批量跑一次最优自替换巡检（给 orchestrator 循环调用）

        Args:
            skills: 要巡检的 skill 列表；None 则巡检已注册的所有基建 skill
        """
        if skills is None:
            skills = list(self._skill_index.keys())
        results = []
        for s in skills:
            # 只巡检有基建 agent 提供的 skill
            has_infra = any(not c.owner_alpha_id and c.status == "approved" and c.is_online
                            for c in self.find_skill(s))
            if not has_infra:
                continue
            try:
                results.append(self.swap_to_best(s, min_score_gain=min_gain))
            except Exception as e:
                logger.warning("最优巡检异常 [%s]: %s", s, e)
                results.append({"skill": s, "action": "error", "error": str(e)})
        return results

    def get_topology(self) -> Dict[str, Any]:
        """返回完整拓扑（nodes + edges），供 /api/v1/a2a/graph 端点和前端可视化"""
        nodes = []
        for node in self._nodes.values():
            nodes.append({
                "id": node.agent_id,
                "name": node.name,
                "type": node.agent_type,
                "endpoint": node.endpoint,
                "skills": node.skills,
                "is_free": node.is_free,
                "is_online": node.is_online,
                "description": node.description,
                "stats": self.get_agent_stats(node.agent_id),
            })

        # edges 去重（相同 caller→target→skill 只保留最近一条）
        seen = {}
        for edge in self._edges:
            key = (edge.caller, edge.target, edge.skill)
            seen[key] = {
                "source": edge.caller,
                "target": edge.target,
                "skill": edge.skill,
                "success": edge.success,
                "latency_ms": edge.latency_ms,
                "timestamp": edge.timestamp,
            }
        edges = list(seen.values())

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_agents": len(nodes),
                "total_edges": len(edges),
                "online_agents": sum(1 for n in nodes if n["is_online"]),
                "free_agents": sum(1 for n in nodes if n["is_free"]),
            },
        }

    def list_skills(self) -> Dict[str, List[str]]:
        """列出所有 skill 及其提供者"""
        return {
            skill: [self._nodes[aid].name for aid in agent_ids if aid in self._nodes]
            for skill, agent_ids in self._skill_index.items()
        }


# ── 全局单例 ──────────────────────────────────────────────────

_global_graph: Optional[AgentGraph] = None


def get_agent_graph() -> AgentGraph:
    """获取全局 AgentGraph 单例"""
    global _global_graph
    if _global_graph is None:
        _global_graph = AgentGraph()
        _bootstrap_internal_agents(_global_graph)
    return _global_graph


def _bootstrap_internal_agents(graph: AgentGraph) -> None:
    """从工具池配置加载基建层 agent（不硬编码，专注架构优化）

    基建层 = 工具池维护者，调用现成的（GitHub 免费 API、开源项目），
    对比同类工具，自动选最优。平台 agent 负责监控和替换。

    配置来源（优先级）：
      1. 环境变量 TOOLPOOL_CONFIG_PATH 指向的 YAML/JSON 文件
      2. ~/.alpha-id/toolpool.json 默认配置
      3. 内置最小默认配置（仅核心 agent，不硬编码工具）
    """
    import os

    config = _load_toolpool_config()

    for agent_cfg in config.get("agents", []):
        try:
            graph.register_agent(AgentNode(
                agent_id=agent_cfg["agent_id"],
                name=agent_cfg["name"],
                agent_type=agent_cfg.get("type", "tool"),
                endpoint=os.getenv(
                    agent_cfg.get("env_endpoint", ""),
                    agent_cfg.get("endpoint", "http://localhost:8000"),
                ),
                skills=agent_cfg.get("skills", []),
                is_free=agent_cfg.get("is_free", True),
                description=agent_cfg.get("description", ""),
                owner_alpha_id="",  # 基建层 agent 无 owner
                status="approved",
                category=agent_cfg.get("category", ""),
            ))
        except Exception as e:
            logger.warning("工具池加载 %s 失败: %s", agent_cfg.get("agent_id", "?"), e)

    logger.info(
        "AgentGraph 工具池加载完成: %d 个基建 agent（从配置加载，非硬编码）",
        len(graph._nodes),
    )


def _load_toolpool_config() -> dict:
    """加载工具池配置（不硬编码，从文件/环境变量加载）

    配置文件格式示例：
    {
      "agents": [
        {
          "agent_id": "tool:moneyprinter",
          "name": "MoneyPrinterTurbo",
          "type": "tool",
          "env_endpoint": "MONEYPRINTER_URL",
          "endpoint": "http://localhost:8080",
          "skills": ["video_generate", "video_status"],
          "is_free": true,
          "category": "视频生成",
          "description": "AI 视频生成（开源）"
        }
      ]
    }
    """
    import json
    import os

    # 1. 环境变量指定的配置文件
    config_path = os.getenv("TOOLPOOL_CONFIG_PATH", "")
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("工具池配置加载失败 %s: %s", config_path, e)

    # 2. 默认配置文件
    default_path = os.path.expanduser("~/.alpha-id/toolpool.json")
    if os.path.exists(default_path):
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("默认工具池配置加载失败: %s", e)

    # 3. 最小默认配置（仅核心调度，工具由用户/管理员添加）
    return {
        "agents": [
            {
                "agent_id": "core:alpha-id",
                "name": "Alpha-ID TwinBrain",
                "type": "core",
                "env_endpoint": "ALPHAID_URL",
                "endpoint": "http://localhost:8000",
                "skills": ["chat", "memory_query", "growth_stats"],
                "is_free": True,
                "category": "核心",
                "description": "数字实体核心运行时",
            },
        ]
    }
