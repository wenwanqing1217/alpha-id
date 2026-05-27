"""
AlphaSocialManager 核心逻辑测试（零 langchain 依赖）
"""

import json
import os
import tempfile

import pytest

from core.alpha_social import AlphaSocialManager
from core.storage import JsonStorage


@pytest.fixture
def manager():
    """每个测试独立临时数据库（注入 JsonStorage）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "social.json")
        storage = JsonStorage(db_path)
        yield AlphaSocialManager(storage=storage)


class TestAlphaSocialManager:
    """AlphaSocialManager 核心功能测试"""

    def test_init_creates_empty_db(self, manager):
        """初始化后数据库文件存在且为空"""
        assert os.path.exists(manager._storage.db_path)
        data = json.load(open(manager._storage.db_path, encoding="utf-8"))
        assert data == {"friends": {}, "friend_requests": {}, "messages": {}}

    def test_send_friend_request_success(self, manager):
        """发送好友请求成功"""
        result = manager.send_friend_request("Alpha-1", "Alpha-002", "你好")
        assert result["success"] is True
        assert "request_id" in result

    def test_send_duplicate_request(self, manager):
        """重复发送待处理请求被拒绝"""
        manager.send_friend_request("Alpha-1", "Alpha-002", "你好")
        result = manager.send_friend_request("Alpha-1", "Alpha-002", " again")
        assert result["success"] is False
        assert "已有待处理" in result["message"]

    def test_accept_friend_request(self, manager):
        """接受好友请求后双向建立好友关系"""
        req = manager.send_friend_request("Alpha-1", "Alpha-002", "hello")
        result = manager.respond_friend_request(req["request_id"], "accept")
        assert result["success"] is True
        assert result["friend_added"] is True

        assert "Alpha-002" in manager.get_friends("Alpha-1")
        assert "Alpha-1" in manager.get_friends("Alpha-002")

    def test_reject_friend_request(self, manager):
        """拒绝好友请求后不建立好友关系"""
        req = manager.send_friend_request("Alpha-1", "Alpha-002", "hello")
        result = manager.respond_friend_request(req["request_id"], "reject")
        assert result["success"] is True
        assert result["friend_added"] is False
        assert manager.get_friends("Alpha-1") == []

    def test_respond_nonexistent_request(self, manager):
        """响应不存在的好友请求"""
        result = manager.respond_friend_request("req_notexist", "accept")
        assert result["success"] is False
        assert "不存在" in result["message"]

    def test_respond_twice(self, manager):
        """重复处理已响应的请求"""
        req = manager.send_friend_request("Alpha-1", "Alpha-002", "hello")
        manager.respond_friend_request(req["request_id"], "accept")
        result = manager.respond_friend_request(req["request_id"], "reject")
        assert result["success"] is False
        assert "已处理" in result["message"]

    def test_send_message_to_nonfriend(self, manager):
        """给非好友发消息被拒绝"""
        result = manager.send_message("Alpha-1", "Alpha-999", "秘密消息")
        assert result["success"] is False
        assert "不是你的好友" in result["message"]

    def test_send_message_to_friend(self, manager):
        """给好友发消息成功"""
        req = manager.send_friend_request("Alpha-1", "Alpha-002", "加好友")
        manager.respond_friend_request(req["request_id"], "accept")

        result = manager.send_message("Alpha-1", "Alpha-002", "你好", "text")
        assert result["success"] is True
        assert result["message_id"].startswith("msg_")

    def test_get_messages(self, manager):
        """获取消息列表"""
        req = manager.send_friend_request("Alpha-1", "Alpha-002", "加好友")
        manager.respond_friend_request(req["request_id"], "accept")
        manager.send_message("Alpha-1", "Alpha-002", "第一条")
        manager.send_message("Alpha-1", "Alpha-002", "第二条")

        messages = manager.get_messages("Alpha-002")
        assert len(messages) == 2
        assert messages[0]["content"] == "第一条"
        assert messages[1]["content"] == "第二条"

    def test_get_unread_messages(self, manager):
        """仅获取未读消息，且获取后标记为已读"""
        req = manager.send_friend_request("Alpha-1", "Alpha-002", "加好友")
        manager.respond_friend_request(req["request_id"], "accept")
        manager.send_message("Alpha-1", "Alpha-002", "未读消息")

        unread = manager.get_messages("Alpha-002", unread_only=True)
        assert len(unread) == 1
        assert unread[0]["content"] == "未读消息"

        # 再次获取未读应为空
        unread_again = manager.get_messages("Alpha-002", unread_only=True)
        assert len(unread_again) == 0

    def test_get_pending_requests(self, manager):
        """获取待处理的请求"""
        manager.send_friend_request("Alpha-003", "Alpha-1", "请求")
        manager.send_friend_request("Alpha-004", "Alpha-1", "请求2")

        pending = manager.get_pending_friend_requests("Alpha-1")
        assert len(pending) == 2

        # 处理后不应再出现
        manager.respond_friend_request(pending[0]["request_id"], "accept")
        pending_after = manager.get_pending_friend_requests("Alpha-1")
        assert len(pending_after) == 1

    def test_already_friends(self, manager):
        """已经是好友时再次发送请求被拒绝"""
        req = manager.send_friend_request("Alpha-1", "Alpha-002", "hello")
        manager.respond_friend_request(req["request_id"], "accept")

        result = manager.send_friend_request("Alpha-1", "Alpha-002", "again")
        assert result["success"] is False
        assert "已经是好友" in result["message"]

    def test_empty_friend_list(self, manager):
        """没有好友时返回空列表"""
        assert manager.get_friends("Alpha-Nobody") == []
        assert manager.get_pending_friend_requests("Alpha-Nobody") == []
