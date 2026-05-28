"""
TwinBrain + AlphaSocialManager 集成测试
使用真实存储，模拟多 Alpha-ID 之间的社交交互全流程。
"""
import pytest
from core.storage import JsonStorage
from core.twin_brain import TwinBrain, BrainSettings
from core.message import Message, MessageType


@pytest.fixture
def storage(tmp_path):
    path = str(tmp_path / "integration.json")
    return JsonStorage(path)


@pytest.fixture
def alice(storage):
    brain = TwinBrain(alpha_id="Alpha-Alice-001", storage=storage, settings=BrainSettings(auto_reply=False))
    brain.awake()
    return brain


@pytest.fixture
def bob(storage):
    brain = TwinBrain(alpha_id="Alpha-Bob-001", storage=storage, settings=BrainSettings(auto_reply=False))
    brain.awake()
    return brain


class TestFriendRequestFlow:
    """好友请求全流程"""

    def test_alice_sends_friend_request_to_bob(self, alice, bob):
        req = Message.create_friend_request(sender="Alpha-Alice-001", recipient="Alpha-Bob-001", note="Hi!")
        resp = bob.receive(req)
        assert resp.success is True
        assert "好友请求已发送" in resp.message

    def test_bob_receives_and_accepts(self, alice, bob):
        # 1. Alice 发请求
        req = Message.create_friend_request(sender="Alpha-Alice-001", recipient="Alpha-Bob-001", note="Hello")
        bob.receive(req)

        # 2. Bob 查看待处理
        pending = bob.social.get_pending_friend_requests("Alpha-Bob-001")
        assert len(pending) == 1
        request_id = pending[0]["request_id"]
        assert pending[0]["from_alpha_id"] == "Alpha-Alice-001"

        # 3. Bob 接受
        accept_msg = Message(
            sender="Alpha-Bob-001",
            recipient="Alpha-Alice-001",
            msg_type=MessageType.FRIEND_RESPONSE,
            payload={"request_id": request_id, "action": "accept"},
        )
        resp = bob.receive(accept_msg)
        assert resp.success is True

        # 4. 验证双向好友（get_friends 返回 List[str]）
        bob_friends = bob.social.get_friends("Alpha-Bob-001")
        assert "Alpha-Alice-001" in bob_friends

        alice_friends = alice.social.get_friends("Alpha-Alice-001")
        assert "Alpha-Bob-001" in alice_friends

    def test_bob_rejects_friend_request(self, alice, bob):
        req = Message.create_friend_request(sender="Alpha-Alice-001", recipient="Alpha-Bob-001", note="Hello")
        bob.receive(req)
        pending = bob.social.get_pending_friend_requests("Alpha-Bob-001")
        request_id = pending[0]["request_id"]

        reject_msg = Message(
            sender="Alpha-Bob-001", recipient="Alpha-Alice-001",
            msg_type=MessageType.FRIEND_RESPONSE,
            payload={"request_id": request_id, "action": "reject"},
        )
        resp = bob.receive(reject_msg)
        assert resp.success is True
        assert "Alpha-Alice-001" not in bob.social.get_friends("Alpha-Bob-001")

    def test_invalid_friend_response_action(self, alice, bob):
        req = Message.create_friend_request(sender="Alpha-Alice-001", recipient="Alpha-Bob-001", note="Hello")
        bob.receive(req)
        pending = bob.social.get_pending_friend_requests("Alpha-Bob-001")

        bad_msg = Message(
            sender="Alpha-Bob-001", recipient="Alpha-Alice-001",
            msg_type=MessageType.FRIEND_RESPONSE,
            payload={"request_id": pending[0]["request_id"], "action": "ban"},
        )
        resp = bob.receive(bad_msg)
        assert resp.success is False
        assert "accept 或 reject" in resp.message

    def test_chat_between_friends(self, alice, bob):
        # 先加好友
        req = Message.create_friend_request(sender="Alpha-Alice-001", recipient="Alpha-Bob-001", note="Hi")
        bob.receive(req)
        pending = bob.social.get_pending_friend_requests("Alpha-Bob-001")
        accept_msg = Message(
            sender="Alpha-Bob-001", recipient="Alpha-Alice-001",
            msg_type=MessageType.FRIEND_RESPONSE,
            payload={"request_id": pending[0]["request_id"], "action": "accept"},
        )
        bob.receive(accept_msg)

        # Alice 给 Bob 发消息
        chat_msg = Message.create_chat(sender="Alpha-Alice-001", recipient="Alpha-Bob-001", text="你好 Bob！")
        resp = bob.receive(chat_msg)
        assert resp.success is True
        assert "已送达" in resp.message

    def test_chat_before_friend(self, alice, bob):
        """未加好友时发消息失败"""
        chat_msg = Message.create_chat(sender="Alpha-Alice-001", recipient="Alpha-Bob-001", text="你好")
        resp = bob.receive(chat_msg)
        assert resp.success is False


class TestProfileVisibility:
    """档案可见度"""

    @pytest.fixture
    def founder_storage(self, tmp_path):
        """创始人专用存储（alpha_id = Alpha-1 与 register_user 匹配）"""
        from core.storage import JsonStorage
        return JsonStorage(str(tmp_path / "founder.json"))

    @pytest.fixture
    def founder(self, founder_storage):
        brain = TwinBrain(alpha_id="Alpha-1", storage=founder_storage, settings=BrainSettings(auto_reply=False))
        brain.awake()
        brain.identity.register_user(device_fingerprint="FOUNDER_DEVICE", is_founder=True, founder_code="Alpha-1-zx")
        return brain

    @pytest.fixture
    def stranger(self, founder_storage):
        brain = TwinBrain(alpha_id="Alpha-Stranger", storage=founder_storage, settings=BrainSettings(auto_reply=False))
        brain.awake()
        return brain

    def test_self_visibility_shows_full(self, founder, stranger):
        """自己看自己看到完整档案"""
        query = Message.create_profile_query(sender="Alpha-1", target="Alpha-1", layer="self")
        resp = founder.receive(query)
        assert resp.success is True
        assert resp.data.get("alpha_id") == "Alpha-1"
        # 自已看应该能看到所有字段
        assert "device_fingerprint" in resp.data

    def test_public_visibility_restricted(self, founder, stranger):
        """陌生人只能看到公开信息"""
        query = Message.create_profile_query(sender="Alpha-Stranger", target="Alpha-1", layer="public")
        resp = founder.receive(query)
        assert resp.success is True
        assert resp.data.get("alpha_id") == "Alpha-1"
        # 陌生人看不到敏感字段
        assert "device_fingerprint" not in resp.data

    def test_friends_visibility(self, founder, stranger):
        """好友能看到比公开更多的信息"""
        # 先加好友
        req = Message.create_friend_request(sender="Alpha-Stranger", recipient="Alpha-1", note="Hi")
        founder.receive(req)
        pending = founder.social.get_pending_friend_requests("Alpha-1")
        accept_msg = Message(
            sender="Alpha-1", recipient="Alpha-Stranger",
            msg_type=MessageType.FRIEND_RESPONSE,
            payload={"request_id": pending[0]["request_id"], "action": "accept"},
        )
        founder.receive(accept_msg)

        query = Message.create_profile_query(sender="Alpha-Stranger", target="Alpha-1", layer="friends")
        resp = founder.receive(query)
        assert resp.success is True
        assert resp.data.get("alpha_id") == "Alpha-1"


class TestBrainInteraction:
    """大脑交互场景"""

    def test_ping(self, alice):
        resp = alice.receive(Message(sender="test", recipient="Alpha-Alice-001", msg_type=MessageType.PING))
        assert resp.success is True
        assert resp.data["alpha_id"] == "Alpha-Alice-001"
        assert resp.data["status"] == "awake"

    def test_sleep_refuses(self, alice):
        alice.sleep()
        msg = Message.create_chat(sender="test", recipient="Alpha-Alice-001", text="Hello")
        resp = alice.receive(msg)
        assert resp.success is False
        assert "不在线" in resp.message

    def test_sleep_auto_reply(self, storage):
        brain = TwinBrain(alpha_id="Alpha-AutoReply", storage=storage,
                          settings=BrainSettings(auto_reply=True, auto_reply_text="我现在不在"))
        brain.sleep()
        msg = Message.create_chat(sender="test", recipient="Alpha-AutoReply", text="Hello")
        resp = brain.receive(msg)
        assert resp.success is True
        assert resp.data.get("auto_reply") is True
        assert resp.message == "我现在不在"

    def test_think_cycle_finds_pending_requests(self, alice, bob):
        req = Message.create_friend_request(sender="Alpha-Alice-001", recipient="Alpha-Bob-001", note="Hello")
        bob.receive(req)
        result = bob.think()
        assert result["pending_requests"] == 1

    def test_app_action(self, alice):
        msg = Message(sender="pet-app", recipient="Alpha-Alice-001",
                      msg_type=MessageType.APP_ACTION,
                      payload={"action": "say", "text": "摸摸头"})
        resp = alice.receive(msg)
        assert resp.success is True
        assert "摸摸头" in resp.message

    def test_unsupported_external_action(self, alice):
        msg = Message(sender="test", recipient="Alpha-Alice-001",
                      msg_type=MessageType.APP_ACTION,
                      payload={"action": "fly"})
        resp = alice.receive(msg)
        assert resp.success is False

    def test_brain_registry_broadcast(self, alice, bob):
        from core.twin_brain import BrainRegistry
        registry = BrainRegistry()
        registry.register(alice)
        registry.register(bob)
        assert registry.count()["total"] == 2

        ping = Message(sender="test", recipient="all", msg_type=MessageType.PING)
        results = registry.broadcast(ping)
        assert len(results) == 2


class TestPersistence:
    """持久化验证"""

    def test_friend_request_survives_reload(self, storage):
        brain = TwinBrain(alpha_id="Alpha-Persist", storage=storage)
        brain.awake()
        req = Message.create_friend_request(sender="Alpha-Other", recipient="Alpha-Persist", note="hi")
        brain.receive(req)

        brain2 = TwinBrain(alpha_id="Alpha-Persist", storage=storage)
        brain2.awake()
        pending = brain2.social.get_pending_friend_requests("Alpha-Persist")
        assert len(pending) >= 1

    def test_friendship_survives_reload(self, storage):
        brain_a = TwinBrain(alpha_id="Alpha-A", storage=storage)
        brain_b = TwinBrain(alpha_id="Alpha-B", storage=storage)
        brain_a.awake()
        brain_b.awake()

        req = Message.create_friend_request(sender="Alpha-A", recipient="Alpha-B", note="hi")
        brain_b.receive(req)
        pending = brain_b.social.get_pending_friend_requests("Alpha-B")
        accept = Message(sender="Alpha-B", recipient="Alpha-A",
                         msg_type=MessageType.FRIEND_RESPONSE,
                         payload={"request_id": pending[0]["request_id"], "action": "accept"})
        brain_b.receive(accept)

        # 重新加载
        reload_a = TwinBrain(alpha_id="Alpha-A", storage=storage)
        assert "Alpha-B" in reload_a.social.get_friends("Alpha-A")

    def test_disjoint_storage(self, tmp_path):
        """不同存储文件互不干扰"""
        storage_a = JsonStorage(str(tmp_path / "a.json"))
        storage_b = JsonStorage(str(tmp_path / "b.json"))
        brain_a = TwinBrain(alpha_id="Alpha-A", storage=storage_a)
        brain_b = TwinBrain(alpha_id="Alpha-B", storage=storage_b)
        brain_a.awake()
        brain_b.awake()

        req = Message.create_friend_request(sender="Alpha-A", recipient="Alpha-B", note="hi")
        brain_b.receive(req)
        pending = brain_b.social.get_pending_friend_requests("Alpha-B")
        accept = Message(sender="Alpha-B", recipient="Alpha-A",
                         msg_type=MessageType.FRIEND_RESPONSE,
                         payload={"request_id": pending[0]["request_id"], "action": "accept"})
        brain_b.receive(accept)

        # B 的存储文件可以加载
        reload_b = TwinBrain(alpha_id="Alpha-B", storage=storage_b)
        assert "Alpha-A" in reload_b.social.get_friends("Alpha-B")

        # A 的存储文件因为不同 storage 所以没有数据
        reload_a = TwinBrain(alpha_id="Alpha-A", storage=storage_a)
        assert reload_a.social.get_friends("Alpha-A") == []
