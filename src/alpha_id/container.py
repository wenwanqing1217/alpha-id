"""
依赖容器 — 替代模块级全局单例

提供：
- 单例管理（在 FastAPI lifespan 中初始化）
- lazy init + 线程安全
- 统一的存储后端切换点
"""

import os
import threading
from typing import Optional

from core.user_identity import UserIdentityManager
from core.alpha_social import AlphaSocialManager
from core.risk_engine import RiskAssessmentEngine
from core.storage import StorageBackend
from core.storage_sqlite import SqliteStorage


class Container:
    """应用级依赖容器"""

    _instance: Optional["Container"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._storage: Optional[StorageBackend] = None
        self._identity: Optional[UserIdentityManager] = None
        self._social: Optional[AlphaSocialManager] = None
        self._risk: Optional[RiskAssessmentEngine] = None

    @classmethod
    def instance(cls) -> "Container":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 存储 ──

    @property
    def storage(self) -> StorageBackend:
        if self._storage is None:
            self._storage = SqliteStorage()
        return self._storage

    @storage.setter
    def storage(self, backend: StorageBackend):
        """允许测试注入 mock 或切换后端"""
        self._storage = backend
        # 重置已创建的 manager，使其下次用新存储重建
        self._identity = None
        self._social = None

    # ── Manager 实例（共享同一存储后端） ──

    @property
    def identity(self) -> UserIdentityManager:
        if self._identity is None:
            self._identity = UserIdentityManager(storage=self.storage)
        return self._identity

    @property
    def social(self) -> AlphaSocialManager:
        if self._social is None:
            self._social = AlphaSocialManager(storage=self.storage)
        return self._social

    @property
    def risk(self) -> RiskAssessmentEngine:
        if self._risk is None:
            self._risk = RiskAssessmentEngine()
        return self._risk

    # ── 生命周期 ──

    def reset(self):
        """测试用：清空所有单例"""
        self._storage = None
        self._identity = None
        self._social = None
        self._risk = None

    def close(self):
        """释放资源"""
        if isinstance(self._storage, SqliteStorage):
            self._storage.close()
