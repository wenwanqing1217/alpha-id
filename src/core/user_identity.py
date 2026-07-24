"""
Alpha-ID 用户身份核心逻辑（无外部依赖）

独立于 langchain 框架的核心业务逻辑，可单独测试。
支持 JSON 文件 / PostgreSQL 双存储后端。
"""

import hashlib
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional

from core.storage import StorageBackend

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """用户档案"""

    alpha_id: str  # Alpha-ID编号
    user_id: str  # 内部唯一标识
    device_fingerprint: str  # 设备指纹
    is_founder: bool  # 是否创始人
    created_at: str  # 创建时间
    last_active: str  # 最后活跃时间
    total_sessions: int  # 总会话次数
    devices: List[str]  # 已绑定设备列表
    status: str  # 状态（active/locked/inactive）


@dataclass
class StatisticsResponse:
    """系统统计信息"""

    total_users: int = 0
    active_users: int = 0
    founder_registered: bool = False
    founder_alpha_id: Optional[str] = None
    next_user_id: str = ""


class UserIdentityManager:
    """用户身份管理器"""

    # 可通过环境变量覆盖，实现多租户配置
    FOUNDER_ALPHA_ID = os.getenv("FOUNDER_ALPHA_ID", "Alpha-1")
    FOUNDER_DEVICE_FINGERPRINT = os.getenv("FOUNDER_DEVICE_FINGERPRINT", "FOUNDER_DEVICE_20250618")
    # 默认 hash = sha256("Alpha-1-zx")，覆盖 FOUNDER_CODE 即可更换
    FOUNDER_CODE_HASH = os.getenv("FOUNDER_CODE_HASH", "2147f64aa8dddda1aa5e6bd13fdebbca87a56b00f7948c9935d17da926a68a29")

    def __init__(self, storage: Optional[StorageBackend] = None):
        # 默认使用 JSON 存储
        if storage is None:
            from core.storage import JsonStorage

            db_path = os.path.join(
                os.getenv("GHOST_WORKSPACE_PATH", os.getcwd()),
                "assets",
                "alpha_id_users.json",
            )
            storage = JsonStorage(db_path)

        self._storage = storage

        # 初始化数据库
        self._init_database()

    def _init_database(self):
        """初始化用户数据库（首次注册时自动创建）"""
        users = self._storage.load("users")
        if users is None:
            self._storage.save("users", {})

        counter = self._storage.load("counter")
        if counter is None:
            self._storage.save("counter", 0)

        founder = self._storage.load("founder_registered")
        if founder is None:
            self._storage.save("founder_registered", False)

    # --- 辅助方法（兼容旧 JSON 结构） ---

    def _load_all(self) -> Dict:
        users = self._storage.load("users") or {}
        counter = self._storage.load("counter") or 0
        founder = self._storage.load("founder_registered") or False
        return {"users": users, "counter": counter, "founder_registered": founder}

    def _save_all(self, data: Dict):
        self._storage.save("users", data.get("users", {}))
        self._storage.save("counter", data.get("counter", 0))
        self._storage.save("founder_registered", data.get("founder_registered", False))

    def register_user(
        self, device_fingerprint: str, is_founder: bool = False, founder_code: Optional[str] = None
    ) -> Dict:
        """
        注册新用户

        Args:
            device_fingerprint: 设备指纹
            is_founder: 是否创始人
            founder_code: 创始人验证码

        Returns:
            注册结果
        """
        db = self._load_all()
        users = db["users"]
        counter = db["counter"]
        founder_registered = db["founder_registered"]

        # 检查设备指纹是否已注册
        for existing_user in users.values():
            if existing_user.get("device_fingerprint") == device_fingerprint:
                logger.warning(f"注册失败: 设备已注册 - {device_fingerprint}")
                return {"success": False, "message": "该设备已注册"}
            if device_fingerprint in existing_user.get("devices", []):
                logger.warning(f"注册失败: 设备已注册 - {device_fingerprint}")
                return {"success": False, "message": "该设备已注册"}

        # 创始人注册逻辑
        if is_founder:
            if hashlib.sha256(founder_code.encode()).hexdigest() != self.FOUNDER_CODE_HASH:
                logger.warning(f"注册失败: 创始人验证码无效 - {device_fingerprint}")
                return {"success": False, "message": "创始人验证码无效"}

            if founder_registered:
                logger.warning(f"注册失败: 创始人已注册 - {device_fingerprint}")
                return {"success": False, "message": "创始人已注册"}

            alpha_id = self.FOUNDER_ALPHA_ID
            founder_registered = True
        else:
            counter += 1
            alpha_id = f"Alpha-{counter:03d}"

        user_id = f"user_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{alpha_id.replace('-', '')}"
        user_profile = UserProfile(
            alpha_id=alpha_id,
            user_id=user_id,
            device_fingerprint=device_fingerprint,
            is_founder=is_founder,
            created_at=datetime.now().isoformat(),
            last_active=datetime.now().isoformat(),
            total_sessions=0,
            devices=[device_fingerprint],
            status="locked",
        )

        users[alpha_id] = asdict(user_profile)

        self._storage.save("users", users)
        self._storage.save("counter", counter)
        self._storage.save("founder_registered", founder_registered)

        logger.info(f"用户注册成功: alpha_id={alpha_id}, user_id={user_id}, is_founder={is_founder}")

        return {
            "success": True,
            "message": f"欢迎加入 Alpha-ID！你的专属编号是：{alpha_id}",
            "alpha_id": alpha_id,
            "user_id": user_id,
            "is_founder": is_founder,
        }

    def get_user_profile(self, alpha_id: str) -> Optional[Dict]:
        """获取用户档案"""
        users = self._storage.load("users") or {}
        return users.get(alpha_id)

    def update_device_binding(self, alpha_id: str, new_device: str) -> Dict:
        """更新设备绑定"""
        users = self._storage.load("users") or {}

        if alpha_id not in users:
            logger.warning(f"设备绑定失败: 用户不存在 - alpha_id={alpha_id}")
            return {"success": False, "message": "用户不存在"}

        user_data = users[alpha_id]

        if new_device not in user_data["devices"]:
            user_data["devices"].append(new_device)

        user_data["device_fingerprint"] = new_device
        user_data["last_active"] = datetime.now().isoformat()

        users[alpha_id] = user_data
        self._storage.save("users", users)

        logger.info(f"设备绑定已更新: alpha_id={alpha_id}, new_device={new_device}, devices={user_data['devices']}")

        return {"success": True, "message": "设备绑定已更新", "devices": user_data["devices"]}

    def sync_cross_device(self, alpha_id: str, from_device: str, to_device: str) -> Dict:
        """
        跨设备同步

        Args:
            alpha_id: Alpha-ID
            from_device: 源设备
            to_device: 目标设备

        Returns:
            同步结果
        """
        users = self._storage.load("users") or {}

        if alpha_id not in users:
            return {"success": False, "message": "用户不存在"}

        user_data = users[alpha_id]

        if from_device not in user_data["devices"]:
            return {"success": False, "message": "源设备未绑定"}

        if to_device not in user_data["devices"]:
            user_data["devices"].append(to_device)

        user_data["last_active"] = datetime.now().isoformat()
        user_data["device_fingerprint"] = to_device

        users[alpha_id] = user_data
        self._storage.save("users", users)

        return {
            "success": True,
            "message": f"跨设备同步完成：{from_device} → {to_device}",
            "alpha_id": alpha_id,
            "total_devices": len(user_data["devices"]),
        }

    def record_session(self, alpha_id: str) -> Dict:
        """记录会话"""
        users = self._storage.load("users") or {}

        if alpha_id not in users:
            return {"success": False, "message": "用户不存在"}

        user_data = users[alpha_id]
        user_data["total_sessions"] += 1
        user_data["last_active"] = datetime.now().isoformat()

        users[alpha_id] = user_data
        self._storage.save("users", users)

        return {
            "success": True,
            "message": "会话已记录",
            "total_sessions": user_data["total_sessions"],
            "last_active": user_data["last_active"],
        }

    def get_statistics(self) -> StatisticsResponse:
        """获取统计信息"""
        users = self._storage.load("users") or {}
        founder_registered = self._storage.load("founder_registered") or False
        counter = self._storage.load("counter") or 0

        total_users = len(users)
        active_users = sum(1 for u in users.values() if u["status"] == "active")

        return StatisticsResponse(
            total_users=total_users,
            active_users=active_users,
            founder_registered=bool(founder_registered),
            founder_alpha_id=self.FOUNDER_ALPHA_ID if founder_registered else None,
            next_user_id=f"Alpha-{counter + 1:03d}" if not founder_registered else "Alpha为创始人保留",
        )

    def get_storage_backend(self) -> StorageBackend:
        """获取当前存储后端（供迁移工具使用）"""
        return self._storage
