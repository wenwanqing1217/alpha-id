"""
Multi-Tenant Engine —— 多租户隔离引擎

所有数据表统一携带 tenant_id，实现：
  - 数据隔离：用户 A 的数据对用户 B 不可见
  - 资源配额：LLM 调用次数、存储、工具限制
  - 租户管理：创建/暂停/恢复/删除租户

用法：
  tenant = TenantManager(storage)
  tenant.create_tenant("user_123", plan="free")
  with tenant.context("user_123") as ctx:
      ctx.check_quota("llm_calls")  # 检查配额
      ctx.emit("message.received", {...})  # 自动注入 tenant_id
"""
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── 租户计划 ──

@dataclass
class TenantPlan:
    """租户套餐"""
    name: str
    max_llm_calls_per_day: int = 100
    max_memory_items: int = 1000
    max_tools: int = 14
    max_storage_mb: int = 100
    max_channels: int = 3
    max_a2a_peers: int = 10
    priority: int = 0  # 调度优先级


# 预定义套餐
PLANS = {
    "free": TenantPlan("free", max_llm_calls_per_day=50, max_memory_items=500, max_tools=5, max_storage_mb=50, max_channels=1, max_a2a_peers=3),
    "pro": TenantPlan("pro", max_llm_calls_per_day=500, max_memory_items=5000, max_tools=14, max_storage_mb=500, max_channels=5, max_a2a_peers=20),
    "enterprise": TenantPlan("enterprise", max_llm_calls_per_day=5000, max_memory_items=50000, max_tools=999, max_storage_mb=5000, max_channels=999, max_a2a_peers=100, priority=10),
}


# ── 租户数据 ──

@dataclass
class Tenant:
    """租户实体"""
    tenant_id: str
    name: str = ""
    plan: str = "free"
    status: str = "active"  # active / suspended / deleted
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 使用统计
    usage: Dict[str, int] = field(default_factory=lambda: {
        "llm_calls_today": 0,
        "memory_items": 0,
        "storage_bytes": 0,
        "last_reset": 0,
    })


# ── 租户上下文 ──

class TenantContext:
    """
    租户上下文 —— 在 with 块内自动注入 tenant_id

    用法：
        with tenant_mgr.context("user_123") as ctx:
            # 所有操作自动携带 tenant_id
            data = {"text": "hello"}
            ctx.enrich(data)  # data 现在包含 tenant_id
            ctx.check_quota("llm_calls")  # 检查配额
    """

    def __init__(self, manager: "TenantManager", tenant_id: str):
        self._manager = manager
        self.tenant_id = tenant_id
        self._tenant: Optional[Tenant] = None

    def __enter__(self):
        self._tenant = self._manager.get_tenant(self.tenant_id)
        if self._tenant is None:
            raise ValueError(f"租户不存在: {self.tenant_id}")
        if self._tenant.status != "active":
            raise PermissionError(f"租户状态异常: {self._tenant.status}")
        return self

    def __exit__(self, *args):
        pass

    def enrich(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """向数据字典注入 tenant_id"""
        data["tenant_id"] = self.tenant_id
        return data

    def check_quota(self, resource: str) -> bool:
        """检查配额是否充足"""
        return self._manager.check_quota(self.tenant_id, resource)

    def increment_usage(self, resource: str, amount: int = 1):
        """增加使用量"""
        self._manager.increment_usage(self.tenant_id, resource, amount)

    @property
    def plan(self) -> TenantPlan:
        """获取当前套餐"""
        return PLANS.get(self._tenant.plan, PLANS["free"])


# ── 租户管理器 ──

class TenantManager:
    """
    租户管理器 —— 管理所有租户的生命周期

    存储后端可选：JSON 文件（开发）/ PostgreSQL（生产）
    """

    def __init__(self, storage=None):
        self._storage = storage
        self._lock = threading.RLock()
        self._tenants: Dict[str, Tenant] = {}
        self._load()

    def _load(self):
        """从存储加载租户"""
        if self._storage is None:
            return
        data = self._storage.load("tenants")
        if data:
            for tid, tdata in data.items():
                self._tenants[tid] = Tenant(**tdata)

    def _save(self):
        """持久化租户"""
        if self._storage is None:
            return
        data = {tid: self._tenant_to_dict(t) for tid, t in self._tenants.items()}
        self._storage.save("tenants", data)

    @staticmethod
    def _tenant_to_dict(tenant: Tenant) -> Dict[str, Any]:
        return {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "plan": tenant.plan,
            "status": tenant.status,
            "created_at": tenant.created_at,
            "metadata": tenant.metadata,
            "usage": tenant.usage,
        }

    # ── CRUD ──

    def create_tenant(self, tenant_id: str = None, name: str = "", plan: str = "free", **metadata) -> Tenant:
        """创建租户"""
        with self._lock:
            if tenant_id is None:
                tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
            if tenant_id in self._tenants:
                raise ValueError(f"租户已存在: {tenant_id}")
            if plan not in PLANS:
                raise ValueError(f"未知套餐: {plan}")

            tenant = Tenant(
                tenant_id=tenant_id,
                name=name or tenant_id,
                plan=plan,
                metadata=metadata,
            )
            self._tenants[tenant_id] = tenant
            self._save()
            logger.info("租户创建: %s (套餐: %s)", tenant_id, plan)
            return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """获取租户"""
        return self._tenants.get(tenant_id)

    def update_tenant(self, tenant_id: str, **kwargs) -> Optional[Tenant]:
        """更新租户属性"""
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return None
            for k, v in kwargs.items():
                if hasattr(tenant, k):
                    setattr(tenant, k, v)
            self._save()
            return tenant

    def suspend_tenant(self, tenant_id: str):
        """暂停租户"""
        self.update_tenant(tenant_id, status="suspended")

    def resume_tenant(self, tenant_id: str):
        """恢复租户"""
        self.update_tenant(tenant_id, status="active")

    def delete_tenant(self, tenant_id: str):
        """删除租户"""
        with self._lock:
            if tenant_id in self._tenants:
                del self._tenants[tenant_id]
                self._save()

    def list_tenants(self, status: str = None) -> List[Tenant]:
        """列出租户"""
        tenants = list(self._tenants.values())
        if status:
            tenants = [t for t in tenants if t.status == status]
        return tenants

    # ── 配额管理 ──

    def check_quota(self, tenant_id: str, resource: str) -> bool:
        """检查配额"""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            return False
        plan = PLANS.get(tenant.plan, PLANS["free"])

        # 每日重置
        now = time.time()
        if now - tenant.usage.get("last_reset", 0) > 86400:
            tenant.usage["llm_calls_today"] = 0
            tenant.usage["last_reset"] = now

        limits = {
            "llm_calls": plan.max_llm_calls_per_day,
            "memory_items": plan.max_memory_items,
            "tools": plan.max_tools,
            "storage_mb": plan.max_storage_mb,
            "channels": plan.max_channels,
            "a2a_peers": plan.max_a2a_peers,
        }

        current = tenant.usage.get(f"{resource.replace('_items', '').replace('_mb', '')}_today" if "calls" in resource else resource, 0)
        limit = limits.get(resource, 999)
        return current < limit

    def increment_usage(self, tenant_id: str, resource: str, amount: int = 1):
        """增加使用量"""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            return
        key = resource if not resource.startswith("llm") else f"{resource}_today"
        tenant.usage[key] = tenant.usage.get(key, 0) + amount
        self._save()

    # ── 上下文 ──

    @contextmanager
    def context(self, tenant_id: str):
        """获取租户上下文（with 语句）"""
        ctx = TenantContext(self, tenant_id)
        with ctx:
            yield ctx


# ── 全局单例 ──

_tenant_manager: Optional[TenantManager] = None


def get_tenant_manager(storage=None) -> TenantManager:
    """获取全局 TenantManager 实例"""
    global _tenant_manager
    if _tenant_manager is None:
        _tenant_manager = TenantManager(storage=storage)
    return _tenant_manager
