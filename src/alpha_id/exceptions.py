"""
Alpha-ID 异常层次结构
====================

定义清晰的异常类型，替代到处使用的 `except Exception: pass`。

异常分类：
- AlphaIDError: 基类
  - TransientError: 可恢复异常（网络超时、限流、连接断开）
    - NetworkError: 网络相关
    - RateLimitError: API 限流
    - ResourceBusyError: 资源暂时不可用
  - PermanentError: 不可恢复异常（数据格式错误、配置错误）
    - ConfigurationError: 配置错误
    - ValidationError: 数据校验失败
    - ResourceExhaustedError: 资源耗尽（GPU OOM 等）
  - SchedulerError: 调度器专用
    - InsufficientGPUError: GPU 不足
    - JobNotFoundError: 任务不存在
    - TenantQuotaExceededError: 租户配额超限

使用原则：
1. 捕获具体异常，不要捕获基类
2. TransientError → 重试/降级
3. PermanentError → 告警/记录
4. 永远不要用 `except Exception: pass`
"""

from __future__ import annotations

from typing import Optional

# ── 基类 ────────────────────────────────────────────────────────

class AlphaIDError(Exception):
    """Alpha-ID 异常基类"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ── 可恢复异常（Transient）─────────────────────────────────────

class TransientError(AlphaIDError):
    """可恢复异常 — 重试或降级处理"""
    pass


class NetworkError(TransientError):
    """网络相关异常（超时、连接断开、DNS 失败）"""

    def __init__(self, message: str, url: str = "", status_code: int = 0):
        super().__init__(message, {"url": url, "status_code": status_code})
        self.url = url
        self.status_code = status_code


class RateLimitError(TransientError):
    """API 限流"""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float = 1.0):
        super().__init__(message, {"retry_after": retry_after})
        self.retry_after = retry_after


class ResourceBusyError(TransientError):
    """资源暂时不可用"""

    def __init__(self, resource_type: str = "", resource_id: str = ""):
        super().__init__(
            f"Resource busy: {resource_type}/{resource_id}",
            {"resource_type": resource_type, "resource_id": resource_id},
        )


# ── 不可恢复异常（Permanent）───────────────────────────────────

class PermanentError(AlphaIDError):
    """不可恢复异常 — 需要人工介入或代码修复"""
    pass


class ConfigurationError(PermanentError):
    """配置错误"""

    def __init__(self, message: str, field: str = ""):
        super().__init__(message, {"field": field})
        self.field = field


class ValidationError(PermanentError):
    """数据校验失败"""

    def __init__(self, message: str, field: str = "", value: str = ""):
        super().__init__(message, {"field": field, "value": value})
        self.field = field


class ResourceExhaustedError(PermanentError):
    """资源耗尽（GPU OOM、磁盘满等）"""

    def __init__(self, resource_type: str = "", required: int = 0, available: int = 0):
        super().__init__(
            f"Resource exhausted: {resource_type} (required={required}, available={available})",
            {"resource_type": resource_type, "required": required, "available": available},
        )
        self.resource_type = resource_type
        self.required = required
        self.available = available


# ── 调度器专用异常 ─────────────────────────────────────────────

class SchedulerError(AlphaIDError):
    """调度器异常基类"""
    pass


class InsufficientGPUError(SchedulerError):
    """GPU 资源不足"""

    def __init__(self, required: int = 0, available: int = 0):
        super().__init__(
            f"Insufficient GPU: required={required}, available={available}",
            {"required": required, "available": available},
        )
        self.required = required
        self.available = available


class JobNotFoundError(SchedulerError):
    """任务不存在"""

    def __init__(self, job_id: str = ""):
        super().__init__(f"Job not found: {job_id}", {"job_id": job_id})
        self.job_id = job_id


class TenantQuotaExceededError(SchedulerError):
    """租户配额超限"""

    def __init__(self, tenant_id: str = "", quota: int = 0, current: int = 0, requested: int = 0):
        super().__init__(
            f"Tenant {tenant_id} quota exceeded: {current}/{quota}, requested {requested}",
            {"tenant_id": tenant_id, "quota": quota, "current": current, "requested": requested},
        )
        self.tenant_id = tenant_id
        self.quota = quota
        self.current = current
        self.requested = requested


# ── 辅助函数 ────────────────────────────────────────────────────

def classify_exception(exc: Exception) -> str:
    """分类异常，返回 'transient' / 'permanent' / 'unknown'"""
    if isinstance(exc, TransientError):
        return "transient"
    elif isinstance(exc, PermanentError):
        return "permanent"
    elif isinstance(exc, AlphaIDError):
        return "permanent"
    else:
        return "unknown"
