"""双链记忆隔离 API 路由"""

from fastapi import APIRouter, Depends, HTTPException

from alpha_id.container import Container, get_container
from auth.middleware import require_user
from core.dual_chain import DualChainManager
from core.storage import StorageBackend

from .models import DualChainMigrateRequest, DualChainQueryRequest, DualChainSaveRequest

router = APIRouter(prefix="/api/v1/dual-chain", tags=["双链记忆"])


def get_storage(storage: StorageBackend = Depends(lambda: None)) -> StorageBackend:
    """占位（不使用）；保留以展示依赖注入模式"""
    pass


def _make_manager(alpha_id: str,
                  container: Container = Depends(get_container)) -> DualChainManager:
    """工厂函数：为指定 alpha_id 创建 DualChainManager

    注意：alpha_id 来自 JWT（require_user），不能在 Depends 中直接获取，
    因此本函数在路由内部调用，而非作为 Depends 使用。
    """
    return DualChainManager(alpha_id=alpha_id, storage=container.storage)


# ── 写入 ──


@router.post("/save")
def dual_chain_save(body: DualChainSaveRequest,
                    alpha_id: str = Depends(require_user),
                    container: Container = Depends(get_container)):
    """保存记忆（自动按敏感度分链）"""
    mgr = DualChainManager(alpha_id=alpha_id, storage=container.storage)
    result = mgr.save(
        content=body.content,
        category=body.category,
        sensitivity=body.sensitivity,
        source=body.source,
        tags=body.tags,
    )
    return result


# ── 读取 ──


@router.get("/get/{memory_id}")
def dual_chain_get(memory_id: str,
                   chain: str = None,
                   alpha_id: str = Depends(require_user),
                   container: Container = Depends(get_container)):
    """获取单条记忆"""
    mgr = DualChainManager(alpha_id=alpha_id, storage=container.storage)
    record = mgr.get(memory_id, chain=chain)
    if record is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return record


@router.post("/query")
def dual_chain_query(body: DualChainQueryRequest,
                     alpha_id: str = Depends(require_user),
                     container: Container = Depends(get_container)):
    """查询记忆"""
    mgr = DualChainManager(alpha_id=alpha_id, storage=container.storage)
    results = mgr.query(
        chain=body.chain,
        keyword=body.keyword,
        category=body.category,
        max_sensitivity=body.max_sensitivity,
        limit=body.limit,
    )
    return {"results": results, "count": len(results)}


# ── 迁移 ──


@router.post("/migrate")
def dual_chain_migrate(body: DualChainMigrateRequest,
                       alpha_id: str = Depends(require_user),
                       container: Container = Depends(get_container)):
    """迁移记忆到另一条链"""
    mgr = DualChainManager(alpha_id=alpha_id, storage=container.storage)
    result = mgr.migrate(body.memory_id, body.target_chain)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ── 统计 ──


@router.get("/stats")
def dual_chain_stats(alpha_id: str = Depends(require_user),
                     container: Container = Depends(get_container)):
    """获取双链统计"""
    mgr = DualChainManager(alpha_id=alpha_id, storage=container.storage)
    stats = mgr.stats()
    return {
        "private_count": stats.private_count,
        "knowledge_count": stats.knowledge_count,
        "total_count": stats.total_count,
        "private_encrypted_ratio": stats.private_encrypted_ratio,
    }


# ── 列出链 ──


@router.get("/list/{chain}")
def dual_chain_list(chain: str,
                    limit: int = 50,
                    alpha_id: str = Depends(require_user),
                    container: Container = Depends(get_container)):
    """列出指定链的记忆"""
    if chain not in ("private", "knowledge"):
        raise HTTPException(status_code=400, detail="chain 必须是 private 或 knowledge")
    mgr = DualChainManager(alpha_id=alpha_id, storage=container.storage)
    results = mgr.list_chain(chain, limit=limit)
    return {"results": results, "count": len(results)}


# ── 删除 ──


@router.delete("/{memory_id}")
def dual_chain_delete(memory_id: str,
                      alpha_id: str = Depends(require_user),
                      container: Container = Depends(get_container)):
    """删除记忆"""
    mgr = DualChainManager(alpha_id=alpha_id, storage=container.storage)
    result = mgr.delete(memory_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result
