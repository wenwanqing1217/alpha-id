"""AgentGraph 核心逻辑测试：注册、查找、统计、基准测试、最优自替换"""
from __future__ import annotations

import pytest

from core.agent_graph import AgentGraph, AgentNode


def make_node(
    agent_id: str,
    skills=(),
    owner: str = "",
    price: int = 0,
    online: bool = True,
    status: str = "approved",
    agent_type: str = "tool",
    is_free: bool = True,
) -> AgentNode:
    return AgentNode(
        agent_id=agent_id,
        name=agent_id,
        agent_type=agent_type,
        endpoint=f"http://localhost:9999/{agent_id}",
        skills=list(skills),
        is_free=is_free,
        is_online=online,
        owner_alpha_id=owner,
        status=status,
        price_credits=price,
    )


class TestAgentGraphBasics:
    def test_register_and_find_skill(self):
        g = AgentGraph()
        g.register_agent(make_node("a1", skills=["ping", "echo"]))
        g.register_agent(make_node("a2", skills=["ping"]))

        found = g.find_skill("ping")
        assert {n.agent_id for n in found} == {"a1", "a2"}
        assert [n.agent_id for n in g.find_skill("echo")] == ["a1"]
        assert g.find_skill("nope") == []

    def test_unregister_cleans_skill_index(self):
        g = AgentGraph()
        g.register_agent(make_node("a1", skills=["ping"]))
        assert g.unregister_agent("a1")
        assert not g.unregister_agent("a1")  # 二次注销返回 False
        assert g.find_skill("ping") == []

    def test_visibility_pending_only_owner(self):
        g = AgentGraph()
        g.register_agent(make_node("draft", skills=["ping"], status="pending", owner="Alpha-1"))

        # 非 owner 看不到 pending
        assert g.find_best_agent("ping", owner_alpha_id="Alpha-2") is None
        # owner 能看到自己的 pending（但 free 策略基建优先，这里只有 draft 所以返回它）
        best = g.find_best_agent("ping", owner_alpha_id="Alpha-1")
        assert best is not None and best.agent_id == "draft"
        # 管理员 include_pending=True 可跨 owner 查看
        best = g.find_best_agent("ping", owner_alpha_id="Alpha-2", include_pending=True)
        assert best is not None and best.agent_id == "draft"


class TestFindBestAgentTiering:
    def _graph_with_market(self) -> AgentGraph:
        g = AgentGraph()
        g.register_agent(make_node("paid-b", skills=["skill-x"], price=5, is_free=False, owner="Other"))
        g.register_agent(make_node("free-a", skills=["skill-x"], owner="Other"))
        g.register_agent(make_node("infra", skills=["skill-x"], owner=""))
        return g

    def test_free_strategy_prefers_infra_over_paid(self):
        g = self._graph_with_market()
        best = g.find_best_agent("skill-x", prefer="free", owner_alpha_id="Alpha-1")
        assert best is not None
        assert best.agent_id == "infra"

    def test_owned_strategy_prefers_own_agent(self):
        g = AgentGraph()
        g.register_agent(make_node("mine", skills=["skill-x"], owner="Alpha-1"))
        g.register_agent(make_node("infra", skills=["skill-x"], owner=""))
        best = g.find_best_agent("skill-x", prefer="owned", owner_alpha_id="Alpha-1")
        assert best is not None and best.agent_id == "mine"

    def test_offline_and_delisted_excluded(self):
        g = AgentGraph()
        g.register_agent(make_node("down", skills=["skill-x"], online=False))
        g.register_agent(make_node("gone", skills=["skill-x"], status="delisted"))
        g.register_agent(make_node("ok", skills=["skill-x"]))
        best = g.find_best_agent("skill-x")
        assert best is not None and best.agent_id == "ok"


class TestRecordCallAndStats:
    def test_record_call_updates_stats(self):
        g = AgentGraph()
        g.register_agent(make_node("a1", skills=["ping"]))
        g.record_call("caller", "a1", "ping", success=True, latency_ms=100)
        g.record_call("caller", "a1", "ping", success=False, latency_ms=200)

        stats = g.get_agent_stats("a1")
        assert stats["call_count"] == 2
        assert stats["success_count"] == 1
        assert stats["fail_count"] == 1
        assert stats["success_rate"] == pytest.approx(0.5)
        assert stats["avg_latency_ms"] == pytest.approx(150)

    def test_preferred_follows_stats(self):
        """记录多次调用后，swap_to_best 应把 preferred 切到更优者"""
        g = AgentGraph()
        g.register_agent(make_node("slow", skills=["skill-x"], owner=""))
        g.register_agent(make_node("fast", skills=["skill-x"], owner=""))

        # 当前 preferred = slow
        g._preferred["skill-x"] = "slow"
        # slow 的历史：1 次失败 1 次慢成功；fast：2 次快速成功
        g.record_call("c", "slow", "skill-x", success=False, latency_ms=900)
        g.record_call("c", "slow", "skill-x", success=True, latency_ms=800)
        g.record_call("c", "fast", "skill-x", success=True, latency_ms=10)
        g.record_call("c", "fast", "skill-x", success=True, latency_ms=12)

        result = g.swap_to_best("skill-x", min_score_gain=5.0)
        assert result["action"] == "swapped"
        assert g._preferred["skill-x"] == "fast"

    def test_swap_keeps_when_no_gain(self):
        g = AgentGraph()
        g.register_agent(make_node("a", skills=["skill-x"], owner=""))
        g.register_agent(make_node("b", skills=["skill-x"], owner=""))
        g._preferred["skill-x"] = "a"
        # 双方均无历史 → 评分相同 → 不替换
        result = g.swap_to_best("skill-x", min_score_gain=5.0)
        assert result["action"] == "kept"


class TestBenchmarkSkill:
    def test_benchmark_ranks_by_score(self):
        g = AgentGraph()
        g.register_agent(make_node("x1", skills=["skill-x"], owner=""))
        g.register_agent(make_node("x2", skills=["skill-x"], owner=""))
        # 双方都有历史：x2 全成功低延迟 → 评分更高
        for _ in range(5):
            g.record_call("c", "x1", "skill-x", success=True, latency_ms=200)
            g.record_call("c", "x1", "skill-x", success=True, latency_ms=200)
            g.record_call("c", "x1", "skill-x", success=False, latency_ms=200)
        for _ in range(5):
            g.record_call("c", "x2", "skill-x", success=True, latency_ms=10)
            g.record_call("c", "x2", "skill-x", success=True, latency_ms=10)

        results = g.benchmark_skill("skill-x")
        assert len(results) == 2
        assert results[0]["agent_id"] == "x2"  # 成功率 100% + 低延迟 → 第一

    def test_benchmark_with_probe(self):
        g = AgentGraph()
        g.register_agent(make_node("x1", skills=["skill-x"], owner=""))
        g.register_agent(make_node("x2", skills=["skill-x"], owner=""))

        def probe(node, params):
            return (True, 5.0) if node.agent_id == "x2" else (False, 999.0)

        results = g.benchmark_skill("skill-x", params={}, probe=probe)
        assert results[0]["agent_id"] == "x2"
        assert results[0]["probed_success"] is True


class TestTopology:
    def test_get_topology_format(self):
        g = AgentGraph()
        g.register_agent(make_node("a1", skills=["ping"]))
        g.register_agent(make_node("a2", skills=["ping"]))
        g.record_call("a1", "a2", "ping", success=True, latency_ms=10)

        topo = g.get_topology()
        assert {n["id"] for n in topo["nodes"]} == {"a1", "a2"}
        assert len(topo["edges"]) == 1
        assert topo["edges"][0]["source"] == "a1"
        assert topo["edges"][0]["target"] == "a2"


class TestExternalSkillMarket:
    """外部 skill 市场源（OpenRouter / Gorilla / 自建注册中心）"""

    def test_register_and_sync_external_skills(self):
        g = AgentGraph()
        g.register_external_source(
            "openrouter",
            "https://openrouter.ai/api",
            {
                "video_generate": [
                    {"id": "runway", "name": "Runway 视频生成", "endpoint": "https://api.runway.example/v1", "is_free": False, "price_credits": 5},
                    {"id": "freevid", "name": "免费视频", "endpoint": "http://free.example/v1", "is_free": True},
                ],
                "channel_copy": [
                    {"id": "copy-ai", "name": "文案 AI", "endpoint": "http://copy.example/v1", "is_free": True},
                ],
            },
        )
        g.register_external_source(
            "gorilla",
            "https://gorilla.example/api",
            {"text_generate": [{"id": "llama", "name": "Llama", "endpoint": "http://llama.example/v1"}]},
        )

        added = g.sync_external_skills()
        assert added == 4  # video_generate×2 + channel_copy×1 + text_generate×1
        # 幂等：重复同步不重复注册
        assert g.sync_external_skills() == 0

        # external agent 已进入 skill 索引，find_skill 能找到
        found = g.find_skill("video_generate")
        assert {n.agent_id for n in found} == {"ext-openrouter-runway", "ext-openrouter-freevid"}
        ext = g.get_agent("ext-openrouter-runway")
        assert ext is not None
        assert ext.agent_type == "external"
        assert ext.is_free is False
        assert ext.price_credits == 5
        assert ext.metadata["source"] == "openrouter"

    def test_sync_single_source_and_list(self):
        g = AgentGraph()
        g.register_external_source("s1", "http://s1.example", {"a": [{"id": "x"}]})
        g.register_external_source("s2", "http://s2.example", {"b": [{"id": "y"}]})

        assert g.sync_external_skills("s1") == 1
        assert g.get_agent("ext-s1-x") is not None
        assert g.get_agent("ext-s2-y") is None

        sources = g.list_external_sources()
        assert {s["name"] for s in sources} == {"s1", "s2"}
        by_name = {s["name"]: s for s in sources}
        assert by_name["s1"]["synced"] is True
        assert by_name["s2"]["synced"] is False

    def test_external_agent_participates_in_find_best_agent(self):
        """外部 agent 同步后应参与选路（作为其他免费候选）"""
        g = AgentGraph()
        g.register_agent(make_node("infra", skills=["translate"], owner=""))
        g.register_external_source("market", "http://m.example", {
            "translate": [{"id": "ext-t", "name": "外部翻译", "endpoint": "http://t.example", "is_free": True}],
        })
        g.sync_external_skills()
        best = g.find_best_agent("translate", prefer="free", owner_alpha_id="Alpha-1")
        assert best is not None
        assert best.agent_id == "infra"  # 基建 tier 优先
        # 移除基建后，外部 agent 成为候选
        g.unregister_agent("infra")
        best = g.find_best_agent("translate", prefer="free", owner_alpha_id="Alpha-1")
        assert best is not None and best.agent_id == "ext-market-ext-t"
