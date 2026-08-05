"""Credits 钱包 + GrowthTracker 成长追踪 + agent_dispatch 内部调度测试"""
from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from core.credits import (
    CreditsManager,
    InsufficientBalanceError,
    DEFAULT_INITIAL_CREDITS,
    DEFAULT_PLATFORM_FEE_RATE,
)
from core.alpha_social import AlphaSocialManager
from core.storage import JsonStorage


@pytest.fixture
def credits_manager():
    """独立临时存储注入（复用 JsonStorage，与 test_alpha_social 一致）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = JsonStorage(os.path.join(tmpdir, "credits.json"))
        social_storage = JsonStorage(os.path.join(tmpdir, "social.json"))
        social = AlphaSocialManager(storage=social_storage)
        yield CreditsManager(storage=storage, social_manager=social)


def _make_friends(social: AlphaSocialManager, a: str, b: str) -> None:
    req = social.send_friend_request(a, b, "hi")
    social.respond_friend_request(req["request_id"], "accept")


class TestCreditsWallet:
    def test_new_wallet_initial_credits(self, credits_manager):
        assert credits_manager.balance("Alpha-New") == DEFAULT_INITIAL_CREDITS

    def test_platform_infra_free(self, credits_manager):
        r = credits_manager.settle_call("Caller-1", "", price_credits=10)
        assert r["charged"] is False
        assert r["reason"] == "platform_infra_free"

    def test_self_owned_free(self, credits_manager):
        r = credits_manager.settle_call("Alpha-1", "Alpha-1", price_credits=10)
        assert r["charged"] is False
        assert r["reason"] == "self_owned_free"

    def test_friend_free(self, credits_manager):
        _make_friends(credits_manager._social, "Alpha-1", "Alpha-2")
        r = credits_manager.settle_call(
            "Alpha-1", "Alpha-2", price_credits=10, is_friend=True
        )
        assert r["charged"] is False
        assert r["reason"] == "friend_free"

    def test_stranger_paid_with_platform_fee(self, credits_manager):
        """陌生人付费：caller 扣 10，owner 得 9，平台抽 1（10%）"""
        caller_before = credits_manager.balance("Alpha-1")
        owner_before = credits_manager.balance("Alpha-2")

        r = credits_manager.settle_call(
            "Alpha-1", "Alpha-2", price_credits=10, agent_id="agent-x", skill="ping"
        )
        assert r["charged"] is True
        assert r["reason"] == "stranger_paid"
        assert r["platform_fee"] == int(10 * DEFAULT_PLATFORM_FEE_RATE)
        assert credits_manager.balance("Alpha-1") == caller_before - 10
        assert credits_manager.balance("Alpha-2") == owner_before + 9

    def test_insufficient_balance_raises(self, credits_manager):
        with pytest.raises(InsufficientBalanceError):
            credits_manager.charge("Alpha-1", 99999, reason="test")

    def test_charge_zero_amount_ok(self, credits_manager):
        tx = credits_manager.charge("Alpha-1", 0, reason="free")
        assert tx.amount == 0

    def test_refund_restores_balance(self, credits_manager):
        before = credits_manager.balance("Alpha-1")
        tx = credits_manager.charge("Alpha-1", 30, reason="a2a_call")
        assert credits_manager.balance("Alpha-1") == before - 30

        refund_tx = credits_manager.refund(tx.tx_id)
        assert refund_tx is not None
        assert credits_manager.balance("Alpha-1") == before

    def test_transactions_history_filtered(self, credits_manager):
        credits_manager.charge("Alpha-1", 5, reason="a2a_call", agent_id="a1")
        credits_manager.reward("Alpha-1", 3, reason="reward")
        txs = credits_manager.get_transactions("Alpha-1", direction="debit")
        assert len(txs) == 1
        assert txs[0]["amount"] == 5
        assert txs[0]["agent_id"] == "a1"


class TestGrowthTracker:
    @pytest.fixture
    def tracker(self):
        from alpha_id.growth_tracker import GrowthTracker
        return GrowthTracker(event_bus=None, memory_store=None)  # 内存模式

    def test_successful_task_adds_exp(self, tracker):
        asyncio.run(tracker._handle_growth_event({
            "alpha_id": "Alpha-1", "tool": "channel_copy", "success": True,
        }))
        stats = asyncio.run(tracker._load_stats("Alpha-1"))
        assert stats["total_exp"] == 2  # channel_copy 奖励 2
        assert stats["total_tasks"] == 1
        assert stats["tool_counts"]["channel_copy"] == 1

    def test_failed_task_no_exp(self, tracker):
        asyncio.run(tracker._handle_growth_event({
            "alpha_id": "Alpha-1", "tool": "video_generate", "success": False,
        }))
        stats = asyncio.run(tracker._load_stats("Alpha-1"))
        assert stats["total_exp"] == 0

    def test_evolution_to_mature(self, tracker):
        """累计 100 成长值 → 进化到成熟体（index 3）"""
        stats = {}
        for tool, times in (("channel_copy", 50),):  # 50 × 2 = 100
            for _ in range(times):
                asyncio.run(tracker._handle_growth_event({
                    "alpha_id": "Alpha-1", "tool": tool, "success": True,
                }))
        stats = asyncio.run(tracker._load_stats("Alpha-1"))
        assert stats["total_exp"] == 100
        assert stats["stage_name"] == "成熟体"
        assert stats["stage_index"] == 3

    def test_stage_info_bounds(self, tracker):
        info = tracker.get_stage_info(0)
        assert info["current"]["name"] == "种子"
        assert info["exp_to_next"] == 10
        top = tracker.get_stage_info(1000)
        assert top["current"]["name"] == "超越体"
        assert top["next"] is None
        assert top["progress"] == 1.0


class TestAgentDispatchInternal:
    def test_internal_growth_skill(self):
        """总助调度器内部 growth_stats 分支（不依赖外部服务）"""
        from api import agent_dispatch
        result = asyncio.run(agent_dispatch._call_internal_alpha_id(
            "growth_stats", {"alpha_id": "Alpha-1", "total_exp": 120}
        ))
        assert result["success"] is True
        assert "stages" in result
        assert result["stage_info"]["current"]["name"] == "成熟体"

    def test_unknown_internal_skill_fails(self):
        from api import agent_dispatch
        result = asyncio.run(agent_dispatch._call_internal_alpha_id(
            "not.a.real.skill", {}
        ))
        assert result["success"] is False
