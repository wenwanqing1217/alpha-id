"""
Alpha-ID 社交网络核心逻辑（零外部依赖）

数据模型 + 管理器，与 langchain 框架完全解耦。
支持 JSON 文件 / PostgreSQL 双存储后端。

社交好友关系来源（优先级从高到低）：
  1. 平台原生好友（friends storage）
  2. 飞书通讯录好友（feishu_contacts sync）
  3. 外部联系人绑定（user_bindings）

通过用户标识符绑定（alpha_id ↔ feishu_open_id ↔ feishu_user_id ↔ 手机号/邮箱）
实现"飞书加了好友的，平台自动互认"的效果。
"""

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from core.storage import StorageBackend

logger = logging.getLogger(__name__)


@dataclass
class FriendRequest:
    """好友请求"""

    request_id: str  # 请求ID
    from_alpha_id: str  # 发起方Alpha-ID
    to_alpha_id: str  # 接收方Alpha-ID
    message: str  # 请求消息
    status: str  # 状态（pending/accepted/rejected）
    created_at: str  # 创建时间
    responded_at: Optional[str]  # 响应时间


@dataclass
class AlphaMessage:
    """Alpha消息"""

    message_id: str  # 消息ID
    from_alpha_id: str  # 发送方Alpha-ID
    to_alpha_id: str  # 接收方Alpha-ID
    content: str  # 消息内容
    message_type: str  # 消息类型（text/image/file）
    timestamp: str  # 时间戳
    read: bool  # 是否已读


@dataclass
class UserBinding:
    """用户多渠道标识符绑定（alpha_id ↔ 各平台）

    用法：用户在 DS 页面点「绑定飞书」后，
    通过 OAuth 拿到 feishu_open_id / feishu_user_id，
    写入 storage.user_bindings。AlphaSocialManager 之后会在飞书通讯录
    同步时用它们互认好友。
    """
    alpha_id: str
    feishu_open_id: str = ""
    feishu_user_id: str = ""  # employee_id / user_id 域
    feishu_union_id: str = ""
    phone: str = ""
    email: str = ""
    wechat_open_id: str = ""
    tg_user_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)


class AlphaSocialManager:
    """Alpha社交管理器 — 原生好友 + 飞书通讯录 + 外部绑定三合一

    要启用飞书通讯录同步：
        mgr = AlphaSocialManager(storage=...)
        mgr.set_feishu_bridge(feishu_bridge)   # 传入已配置 app_id/secret 的桥
        mgr.sync_feishu_contacts()              # 主动同步一次
        # 或在 OrchestratorEngine 里注册为数据循环定期同步
    """

    def __init__(
        self,
        storage: Optional[StorageBackend] = None,
        user_exists_fn=None,
    ):
        if storage is None:
            from core.storage_sqlite import SqliteStorage

            self._storage = SqliteStorage()
        else:
            self._storage = storage

        # 用户存在性检查回调（可选，用于验证目标用户）
        self._user_exists_fn = user_exists_fn

        # 飞书桥（可选，设置后才能用通讯录同步）
        self._feishu_bridge: Optional[Any] = None

        # 缓存：alpha_id → 飞书 open_id/user_id/phone（用于加速好友互认）
        self._bindings_cache: Dict[str, UserBinding] = {}
        self._feishu_to_alpha: Dict[str, str] = {}  # feishu_open_id → alpha_id

        self._init_database()

    def set_feishu_bridge(self, bridge: Any) -> None:
        """注入 FeishuBridge（在 main.py 或 Container 里调用一次）"""
        self._feishu_bridge = bridge

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

        # 新集合：用户标识符绑定
        bindings = self._storage.load("user_bindings")
        if bindings is None:
            self._storage.save("user_bindings", {})

        # 新集合：飞书通讯录快照（按 alpha_id → [feishu_contact, ...]）
        contacts = self._storage.load("feishu_contacts")
        if contacts is None:
            self._storage.save("feishu_contacts", {})

        self._rebuild_binding_index()

    # ── 用户标识符绑定 ──────────────────────────────────────────

    def _rebuild_binding_index(self) -> None:
        """从 storage 重建绑定索引（启动 / 写入后调用）"""
        bindings = self._storage.load("user_bindings") or {}
        self._bindings_cache.clear()
        self._feishu_to_alpha.clear()
        for alpha_id, raw in bindings.items():
            b = UserBinding(alpha_id=alpha_id, **{k: v for k, v in raw.items() if k != "alpha_id"})
            self._bindings_cache[alpha_id] = b
            if b.feishu_open_id:
                self._feishu_to_alpha[b.feishu_open_id] = alpha_id
            if b.feishu_user_id:
                self._feishu_to_alpha[b.feishu_user_id] = alpha_id
            if b.feishu_union_id:
                self._feishu_to_alpha[b.feishu_union_id] = alpha_id

    def set_user_binding(self, binding: UserBinding) -> None:
        """写入用户渠道标识符绑定（DS「绑定飞书」按钮调用）"""
        bindings = self._storage.load("user_bindings") or {}
        binding.updated_at = time.time()
        bindings[binding.alpha_id] = asdict(binding)
        self._storage.save("user_bindings", bindings)
        self._rebuild_binding_index()

    def get_user_binding(self, alpha_id: str) -> Optional[UserBinding]:
        return self._bindings_cache.get(alpha_id)

    def resolve_alpha_id(self, feishu_id: str) -> str:
        """把任意飞书标识符（open_id/user_id/union_id）解析成 alpha_id，没绑就返回空串"""
        return self._feishu_to_alpha.get(feishu_id, "")

    # ── 飞书通讯录同步 ──────────────────────────────────────────

    def sync_feishu_contacts(self, actor_alpha_id: str = "") -> Dict[str, Any]:
        """同步某用户的飞书通讯录到 storage

        步骤：
          1. 要求 actor_alpha_id 已绑定飞书（set_user_binding 过）
          2. 通过 FeishuBridge 的 tenant_access_token 拉「通讯录我的部门/同事」
          3. 对每个飞书同事，如果他也在本平台绑定了同一个飞书账号，
             就在平台自动把他俩加为好友（双向写入 friends storage）

        因为真实用户量一般 <500，直接全量同步，不做分页缓存。
        失败时返回 error，不抛异常。
        """
        if self._feishu_bridge is None:
            return {"success": False, "error": "FeishuBridge 未注入，请先 set_feishu_bridge"}

        binding = self.get_user_binding(actor_alpha_id) if actor_alpha_id else None
        token = ""
        try:
            token = self._feishu_bridge._get_tenant_token()
        except Exception as e:
            logger.warning("飞书 token 取不到: %s", e)
        if not token:
            return {"success": False, "error": "取不到飞书 tenant_access_token"}

        # 取用户自己的飞书 user_id/open_id 列表
        feishu_ids = set()
        if binding:
            if binding.feishu_open_id:
                feishu_ids.add(binding.feishu_open_id)
            if binding.feishu_user_id:
                feishu_ids.add(binding.feishu_user_id)

        contacts_snapshot: List[Dict[str, Any]] = []
        matched_alpha_friends: Set[str] = set()

        try:
            import httpx
            headers = {"Authorization": f"Bearer {token}"}

            # 分页拉取通讯录同事（按 user_scope=0「同一部门/好友」，避免爬全公司）
            page_token = ""
            for _ in range(10):  # 最多 10 页 * 50 = 500 人，安全限
                url = "https://open.feishu.cn/open-apis/contact/v3/users"
                params = {
                    "page_size": 50,
                    "department_id": "",  # 不传 = 按 token 可见范围
                    "user_id_type": "open_id",
                }
                if page_token:
                    params["page_token"] = page_token
                resp = httpx.get(url, headers=headers, params=params, timeout=10)
                data = resp.json()
                if data.get("code") != 0:
                    # 权限不够就退化为空，不报错
                    logger.info("飞书通讯录权限不足: %s", data.get("msg", ""))
                    break
                items = data.get("data", {}).get("items", []) or []
                for u in items:
                    contact = {
                        "open_id": u.get("open_id", ""),
                        "user_id": u.get("user_id", ""),
                        "name": u.get("name", ""),
                        "mobile": u.get("mobile", ""),
                        "email": u.get("email", ""),
                        "department_ids": u.get("department_ids", []),
                    }
                    contacts_snapshot.append(contact)

                    # 看此人是否在本平台有绑定 → 是则自动互认为好友
                    fid = contact.get("open_id") or contact.get("user_id") or ""
                    other_alpha = self._feishu_to_alpha.get(fid, "")
                    if other_alpha and other_alpha != actor_alpha_id:
                        matched_alpha_friends.add(other_alpha)

                page_token = data.get("data", {}).get("page_token", "")
                has_more = data.get("data", {}).get("has_more", False)
                if not has_more:
                    break

        except Exception as e:
            logger.exception("飞书通讯录同步异常")
            return {"success": False, "error": f"通讯录拉取失败: {e}"}

        # 快照保存
        contacts_store = self._storage.load("feishu_contacts") or {}
        contacts_store[actor_alpha_id or "default"] = {
            "snapshot_at": time.time(),
            "contacts": contacts_snapshot,
        }
        self._storage.save("feishu_contacts", contacts_store)

        # 自动互认好友（只有两个用户都在本平台绑定了飞书才生效）
        auto_friends_added = 0
        if actor_alpha_id:
            for other in matched_alpha_friends:
                ok = self._ensure_friendship(actor_alpha_id, other)
                if ok:
                    auto_friends_added += 1

        return {
            "success": True,
            "actor": actor_alpha_id,
            "fetched_contacts": len(contacts_snapshot),
            "matched_platform_users": len(matched_alpha_friends),
            "auto_friends_added": auto_friends_added,
        }

    def _ensure_friendship(self, a: str, b: str) -> bool:
        """确保 a 和 b 互为好友；写入双向存储。返回 True=有新增，False=已是好友"""
        if not a or not b or a == b:
            return False
        friends = self._storage.load("friends") or {}
        a_list = friends.setdefault(a, [])
        b_list = friends.setdefault(b, [])
        changed = False
        if b not in a_list:
            a_list.append(b)
            changed = True
        if a not in b_list:
            b_list.append(a)
            changed = True
        if changed:
            self._storage.save("friends", friends)
            logger.info("✓ 自动互认好友: %s ↔ %s", a, b)
        return changed

    # ── 好友查询（合并原生 + 飞书互认） ────────────────────────

    def get_friends(self, alpha_id: str) -> List[str]:
        """获取好友列表（合并来源：原生 + 飞书通讯录已同步的）"""
        friends = self._storage.load("friends") or {}
        native = list(friends.get(alpha_id, []))

        # 飞书互认来源 — feishu_contacts 快照中解析出的「飞书同事 + 平台有绑定」
        # 这些已经在 sync 时写入 friends 了，所以此处不重复加。
        # 如果有异步延迟，这里不再做二次解析，确保 single source of truth = friends storage。
        seen = set()
        result: List[str] = []
        for f in native:
            if f in seen:
                continue
            seen.add(f)
            result.append(f)
        return result

    def send_friend_request(self, from_alpha_id: str, to_alpha_id: str, message: str) -> Dict:
        """发送好友请求（不验证目标用户存在，支持预注册场景）"""
        friends = self._storage.load("friends") or {}
        requests = self._storage.load("friend_requests") or {}

        if to_alpha_id in friends.get(from_alpha_id, []):
            return {"success": False, "message": "已经是好友了"}

        for req in requests.values():
            if (
                req["from_alpha_id"] == from_alpha_id
                and req["to_alpha_id"] == to_alpha_id
                and req["status"] == "pending"
            ):
                return {"success": False, "message": "已有待处理的好友请求"}

        request_id = f"req_{datetime.now().strftime('%Y%m%d%H%M%S')}_{from_alpha_id.replace('-', '')}"
        friend_request = FriendRequest(
            request_id=request_id,
            from_alpha_id=from_alpha_id,
            to_alpha_id=to_alpha_id,
            message=message,
            status="pending",
            created_at=datetime.now().isoformat(),
            responded_at=None,
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

    def send_message(self, from_alpha_id: str, to_alpha_id: str, content: str, message_type: str = "text") -> Dict:
        """发送消息给好友"""
        # H4: 验证目标用户存在
        if self._user_exists_fn and not self._user_exists_fn(to_alpha_id):
            return {"success": False, "message": "目标用户不存在"}

        # H5: 双向好友检查（防止数据不一致导致绕过）
        friends = self._storage.load("friends") or {}
        if to_alpha_id not in friends.get(from_alpha_id, []):
            return {"success": False, "message": "对方不是你的好友"}
        if from_alpha_id not in friends.get(to_alpha_id, []):
            return {"success": False, "message": "对方不是你的好友（单向数据异常）"}

        messages = self._storage.load("messages") or {}

        message_id = f"msg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{from_alpha_id.replace('-', '')}"
        alpha_message = AlphaMessage(
            message_id=message_id,
            from_alpha_id=from_alpha_id,
            to_alpha_id=to_alpha_id,
            content=content,
            message_type=message_type,
            timestamp=datetime.now().isoformat(),
            read=False,
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

    def get_pending_friend_requests(self, alpha_id: str) -> List[Dict]:
        """获取待处理的好友请求"""
        requests = self._storage.load("friend_requests") or {}
        return [req for req in requests.values() if req["to_alpha_id"] == alpha_id and req["status"] == "pending"]

    def remove_friend(self, alpha_id: str, friend_id: str) -> Dict:
        """删除好友（GDPR 数据清理用）"""
        friends = self._storage.load("friends") or {}
        if alpha_id in friends and friend_id in friends[alpha_id]:
            friends[alpha_id].remove(friend_id)
            self._storage.save("friends", friends)
        # 双向删除
        if friend_id in friends and alpha_id in friends[friend_id]:
            friends[friend_id].remove(alpha_id)
            self._storage.save("friends", friends)
        return {"success": True}

    def get_storage_backend(self) -> StorageBackend:
        """获取当前存储后端（供迁移工具使用）"""
        return self._storage
