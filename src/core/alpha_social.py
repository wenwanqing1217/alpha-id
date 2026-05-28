"""
Alpha-ID 社交网络核心逻辑（零外部依赖）

数据模型 + 管理器，与 langchain 框架完全解耦。
支持 JSON 文件 / PostgreSQL 双存储后端。
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional

from core.storage import StorageBackend
from core.storage_sqlite import SqliteStorage


@dataclass
class FriendRequest:
    """好友请求"""
    request_id: str            # 请求ID
    from_alpha_id: str         # 发起方Alpha-ID
    to_alpha_id: str           # 接收方Alpha-ID
    message: str               # 请求消息
    status: str                # 状态（pending/accepted/rejected）
    created_at: str            # 创建时间
    responded_at: Optional[str]  # 响应时间


@dataclass
class AlphaMessage:
    """Alpha消息"""
    message_id: str            # 消息ID
    from_alpha_id: str         # 发送方Alpha-ID
    to_alpha_id: str           # 接收方Alpha-ID
    content: str               # 消息内容
    message_type: str          # 消息类型（text/image/file）
    timestamp: str             # 时间戳
    read: bool                 # 是否已读


class AlphaSocialManager:
    """Alpha社交管理器"""

    def __init__(self, storage: Optional[StorageBackend] = None):
        if storage is None:
            db_path = os.path.join(
                os.getenv("COZE_WORKSPACE_PATH", os.getcwd()),
                "assets",
                "alpha_id.db"
            )
            storage = SqliteStorage(db_path)
        else:
            self._storage = storage

        self._init_database()

    def _init_database(self):
        """初始化数据库"""
        friends = self._storage.load("friends")
        if friends is None:
            self._storage.save("friends", {})

        requests = self._storage.load("friend_requests")
        if requests is None:
            self._storage.save("friend_requests", {})

        messages = self._storage.load("messages")
        if messages is None:
            self._storage.save("messages", {})

    def send_friend_request(self, from_alpha_id: str, to_alpha_id: str, message: str) -> Dict:
        """发送好友请求"""
        friends = self._storage.load("friends") or {}
        requests = self._storage.load("friend_requests") or {}

        if to_alpha_id in friends.get(from_alpha_id, []):
            return {"success": False, "message": "已经是好友了"}

        for req in requests.values():
            if (req["from_alpha_id"] == from_alpha_id
                    and req["to_alpha_id"] == to_alpha_id
                    and req["status"] == "pending"):
                return {"success": False, "message": "已有待处理的好友请求"}

        request_id = f"req_{datetime.now().strftime('%Y%m%d%H%M%S')}_{from_alpha_id.replace('-', '')}"
        friend_request = FriendRequest(
            request_id=request_id,
            from_alpha_id=from_alpha_id,
            to_alpha_id=to_alpha_id,
            message=message,
            status="pending",
            created_at=datetime.now().isoformat(),
            responded_at=None
        )

        requests[request_id] = asdict(friend_request)
        self._storage.save("friend_requests", requests)

        return {"success": True, "message": "好友请求已发送", "request_id": request_id}

    def respond_friend_request(self, request_id: str, response: str) -> Dict:
        """响应好友请求（accept/reject）"""
        requests = self._storage.load("friend_requests") or {}

        if request_id not in requests:
            return {"success": False, "message": "好友请求不存在"}

        request = requests[request_id]
        if request["status"] != "pending":
            return {"success": False, "message": "请求已处理"}

        request["status"] = response
        request["responded_at"] = datetime.now().isoformat()

        if response == "accept":
            from_id = request["from_alpha_id"]
            to_id = request["to_alpha_id"]
            friends = self._storage.load("friends") or {}
            if from_id not in friends:
                friends[from_id] = []
            if to_id not in friends:
                friends[to_id] = []
            friends[from_id].append(to_id)
            friends[to_id].append(from_id)
            self._storage.save("friends", friends)

        requests[request_id] = request
        self._storage.save("friend_requests", requests)

        if response == "accept":
            return {"success": True, "message": "已接受好友请求", "friend_added": True}
        else:
            return {"success": True, "message": "已拒绝好友请求", "friend_added": False}

    def send_message(self, from_alpha_id: str, to_alpha_id: str,
                     content: str, message_type: str = "text") -> Dict:
        """发送消息给好友"""
        friends = self._storage.load("friends") or {}

        if to_alpha_id not in friends.get(from_alpha_id, []):
            return {"success": False, "message": "对方不是你的好友"}

        messages = self._storage.load("messages") or {}

        message_id = f"msg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{from_alpha_id.replace('-', '')}"
        alpha_message = AlphaMessage(
            message_id=message_id,
            from_alpha_id=from_alpha_id,
            to_alpha_id=to_alpha_id,
            content=content,
            message_type=message_type,
            timestamp=datetime.now().isoformat(),
            read=False
        )

        if to_alpha_id not in messages:
            messages[to_alpha_id] = []
        messages[to_alpha_id].append(asdict(alpha_message))
        self._storage.save("messages", messages)

        return {"success": True, "message": "消息已发送", "message_id": message_id}

    def get_messages(self, alpha_id: str, unread_only: bool = False) -> List[Dict]:
        """获取消息列表"""
        messages = self._storage.load("messages") or {}
        items = messages.get(alpha_id, [])

        if unread_only:
            items = [m for m in items if not m["read"]]
            # 标记为已读
            all_items = messages.get(alpha_id, [])
            for m in all_items:
                if not m["read"]:
                    m["read"] = True
            messages[alpha_id] = all_items
            self._storage.save("messages", messages)

        return items

    def get_friends(self, alpha_id: str) -> List[str]:
        """获取好友列表"""
        friends = self._storage.load("friends") or {}
        return friends.get(alpha_id, [])

    def get_pending_friend_requests(self, alpha_id: str) -> List[Dict]:
        """获取待处理的好友请求"""
        requests = self._storage.load("friend_requests") or {}
        return [
            req for req in requests.values()
            if req["to_alpha_id"] == alpha_id and req["status"] == "pending"
        ]

    def get_storage_backend(self) -> StorageBackend:
        """获取当前存储后端（供迁移工具使用）"""
        return self._storage
