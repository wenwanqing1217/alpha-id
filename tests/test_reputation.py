"""
ReputationEngine 信誉图谱单元测试
"""

from core.reputation import ReputationEngine, ReputationScore
from core.storage import JsonStorage


def test_compute_basic_score():
    """基础信誉评分计算"""
    engine = ReputationEngine(alpha_id="Alpha-Test-001")
    score = engine.compute(
        active_hours=6.0,
        total_uptime_hours=48.0,
        friend_count=5,
        friend_accept_rate=1.0,
        messages_sent=10,
        messages_received=10,
        error_count=0,
        is_awake=True,
    )
    assert score.composite > 0
    assert score.activity >= 15.0  # awake 保底
    assert score.social >= 25.0  # 5 friends * 5 + 1.0 * 50
    assert score.quality > 80.0  # 1:1 ratio
    assert score.stability > 60.0  # 48h uptime + no errors


def test_compute_low_score():
    """低信誉场景"""
    engine = ReputationEngine(alpha_id="Alpha-Test-002")
    score = engine.compute(
        active_hours=0.0,
        total_uptime_hours=0.5,
        friend_count=0,
        friend_accept_rate=0.0,
        messages_sent=100,
        messages_received=0,
        error_count=5,
        is_awake=False,
    )
    assert score.composite < 40.0  # 低分
    assert score.activity == 0.0
    assert score.social == 0.0  # 0 friends + 0 accept rate
    assert score.quality < 20.0  # 全是发送，严重偏差


def test_compute_mid_score():
    """中等信誉场景"""
    engine = ReputationEngine(alpha_id="Alpha-Test-003")
    score = engine.compute(
        active_hours=12.0,
        total_uptime_hours=72.0,
        friend_count=3,
        friend_accept_rate=0.8,
        messages_sent=30,
        messages_received=20,
        error_count=1,
        is_awake=True,
    )
    assert 30.0 <= score.composite <= 95.0
    assert score.activity >= 15.0
    assert 40.0 <= score.social <= 80.0  # 3*5 + 0.8*50 = 15+40 = 55
    assert score.quality > 40.0  # ratio=0.6, quality=100-0.1*200=80


def test_score_levels():
    """等级标签边界测试"""
    # D 级
    s = ReputationScore("Alpha", 20, 10, 10, 10, 10, 0, "")
    assert s.level == "D"
    # C 级
    s = ReputationScore("Alpha", 35, 10, 10, 10, 10, 0, "")
    assert s.level == "C"
    # B 级
    s = ReputationScore("Alpha", 55, 10, 10, 10, 10, 0, "")
    assert s.level == "B"
    # A 级
    s = ReputationScore("Alpha", 75, 10, 10, 10, 10, 0, "")
    assert s.level == "A"
    # S 级
    s = ReputationScore("Alpha", 90, 10, 10, 10, 10, 0, "")
    assert s.level == "S"


def test_persistence(tmp_path):
    """评分持久化"""
    db_file = str(tmp_path / "rep.json")
    storage = JsonStorage(db_file)
    engine = ReputationEngine(alpha_id="Alpha-Persist-001", storage=storage)

    # 第一次计算
    engine.compute(
        active_hours=10.0,
        total_uptime_hours=100.0,
        friend_count=8,
        friend_accept_rate=1.0,
        messages_sent=50,
        messages_received=60,
        error_count=0,
        is_awake=True,
    )

    # 新引擎实例读取已有数据
    engine2 = ReputationEngine(alpha_id="Alpha-Persist-001", storage=storage)
    latest = engine2.get_latest()
    assert latest is not None
    assert latest.activity > 0
    assert latest.social > 0


def test_get_history(tmp_path):
    """历史记录跟踪"""
    db_file = str(tmp_path / "rep_history.json")
    storage = JsonStorage(db_file)
    engine = ReputationEngine(alpha_id="Alpha-Hist-001", storage=storage)

    # 计算 3 次
    for i in range(3):
        engine.compute(
            active_hours=float(i + 1),
            total_uptime_hours=10.0,
            friend_count=i,
            friend_accept_rate=1.0,
            messages_sent=i * 10,
            messages_received=i * 10,
            error_count=0,
            is_awake=True,
        )

    history = engine.get_history()
    assert len(history) == 3
    assert history[-1]["composite"] > history[0]["composite"]  # 趋势上升


def test_get_latest_returns_none_when_no_data():
    """无数据时 get_latest 返回 None"""
    engine = ReputationEngine(alpha_id="Alpha-None-001")
    assert engine.get_latest() is None
    assert engine.get_level() == "N/A"


def test_get_all_scores(tmp_path):
    """批量获取所有评分"""
    db_file = str(tmp_path / "rep_all.json")
    storage = JsonStorage(db_file)

    # 两个不同大脑
    for aid in ["Alpha-A", "Alpha-B"]:
        engine = ReputationEngine(alpha_id=aid, storage=storage)
        engine.compute(
            active_hours=5.0,
            total_uptime_hours=20.0,
            friend_count=3,
            friend_accept_rate=1.0,
            messages_sent=10,
            messages_received=10,
            error_count=0,
            is_awake=True,
        )

    all_scores = ReputationEngine.get_all_scores(storage)
    assert len(all_scores) == 2
    assert "Alpha-A" in all_scores
    assert "Alpha-B" in all_scores


def test_leaderboard(tmp_path):
    """排行榜排序正确"""
    db_file = str(tmp_path / "rep_lead.json")
    storage = JsonStorage(db_file)

    # 高分和低分
    engine_a = ReputationEngine(alpha_id="Alpha-High", storage=storage)
    engine_a.compute(
        active_hours=100.0,  # 满分活跃
        total_uptime_hours=500.0,
        friend_count=20,
        friend_accept_rate=1.0,
        messages_sent=100,
        messages_received=100,
        error_count=0,
        is_awake=True,
    )

    engine_b = ReputationEngine(alpha_id="Alpha-Low", storage=storage)
    engine_b.compute(
        active_hours=0.5,
        total_uptime_hours=1.0,
        friend_count=0,
        friend_accept_rate=0.0,
        messages_sent=0,
        messages_received=0,
        error_count=5,
        is_awake=False,
    )

    rankings = ReputationEngine.get_leaderboard(storage, top_n=10)
    assert len(rankings) == 2
    assert rankings[0]["alpha_id"] == "Alpha-High"
    assert rankings[0]["composite"] > rankings[1]["composite"]
