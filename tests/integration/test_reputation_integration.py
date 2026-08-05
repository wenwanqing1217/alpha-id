"""
TwinBrain × ReputationEngine 集成测试

验证 compute_reputation() 和信誉评分在 status/think 中的展现。
"""

from core.storage import JsonStorage
from core.twin_brain import BrainSettings, TwinBrain


def test_compute_reputation_in_status(tmp_path):
    """get_status() 包含信誉评分"""
    db_file = str(tmp_path / "integ_rep.json")
    storage = JsonStorage(db_file)
    brain = TwinBrain(
        alpha_id="Alpha-Int-001",
        storage=storage,
        settings=BrainSettings(auto_reply=False, use_agent_chat=False),
    )
    brain.awake()

    status = brain.get_status()
    assert "reputation" in status
    rep = status["reputation"]
    assert "composite" in rep
    assert "activity" in rep
    assert "social" in rep
    assert "quality" in rep
    assert "stability" in rep
    assert "level" in rep
    assert rep["composite"] >= 0


def test_compute_reputation_in_think(tmp_path):
    """think() 包含信誉评分"""
    db_file = str(tmp_path / "integ_think_rep.json")
    storage = JsonStorage(db_file)
    brain = TwinBrain(
        alpha_id="Alpha-Int-002",
        storage=storage,
        settings=BrainSettings(auto_reply=False, use_agent_chat=False),
    )
    brain.awake()

    result = brain.think()
    assert "reputation" in result
    assert result["reputation"]["composite"] >= 0


def test_reputation_grows_with_activity(tmp_path):
    """活跃度增加后信誉上升"""
    db_file = str(tmp_path / "integ_rep_up.json")
    storage = JsonStorage(db_file)
    brain = TwinBrain(
        alpha_id="Alpha-Int-003",
        storage=storage,
        settings=BrainSettings(auto_reply=False, use_agent_chat=False),
    )
    brain.awake()

    # 初评
    rep1 = brain.compute_reputation()

    # 模拟大量活跃
    brain._message_count = 100
    brain.active_since = 0  # 模拟长时间在线（实际用 mock 时间不现实）

    # 用高参数模拟活跃
    score = brain.reputation.compute(
        active_hours=48.0,
        total_uptime_hours=100.0,
        friend_count=10,
        friend_accept_rate=1.0,
        messages_sent=200,
        messages_received=200,
        error_count=0,
        is_awake=True,
    )
    assert score.composite > rep1["composite"]


def test_reputation_persists_across_brain_instances(tmp_path):
    """信誉评分跨大脑实例持久化"""
    db_file = str(tmp_path / "integ_rep_persist.json")
    storage = JsonStorage(db_file)

    # 第一个实例
    brain1 = TwinBrain(
        alpha_id="Alpha-Int-004",
        storage=storage,
        settings=BrainSettings(auto_reply=False, use_agent_chat=False),
    )
    brain1.awake()
    brain1.compute_reputation()

    # 第二个实例，同 storage 同 alpha_id
    brain2 = TwinBrain(
        alpha_id="Alpha-Int-004",
        storage=storage,
        settings=BrainSettings(auto_reply=False, use_agent_chat=False),
    )
    brain2.awake()
    latest = brain2.reputation.get_latest()
    assert latest is not None
    assert latest.composite > 0


def test_sleeping_brain_has_lower_reputation(tmp_path):
    """休眠状态信誉更低（is_awake=False 影响活跃度保底）"""
    db_file = str(tmp_path / "integ_rep_sleep.json")
    storage = JsonStorage(db_file)

    awake_brain = TwinBrain(
        alpha_id="Alpha-Awake",
        storage=storage,
        settings=BrainSettings(auto_reply=False, use_agent_chat=False),
    )
    awake_brain.awake()

    sleep_brain = TwinBrain(
        alpha_id="Alpha-Sleep",
        storage=storage,
        settings=BrainSettings(auto_reply=False, use_agent_chat=False),
    )

    rep_awake = awake_brain.compute_reputation()
    rep_sleep = sleep_brain.compute_reputation()
    assert rep_awake["activity"] >= rep_sleep["activity"]


def test_reputation_levels_in_status(tmp_path):
    """get_status() 包含等级"""
    db_file = str(tmp_path / "integ_rep_level.json")
    storage = JsonStorage(db_file)

    brain = TwinBrain(alpha_id="Alpha-Level", storage=storage)
    brain.awake()
    status = brain.get_status()
    assert status["reputation"]["level"] in ("S", "A", "B", "C", "D")
