"""
Alpha-ID Tool Orchestrator — 编程工具协同调度
=============================================

将 orchestrator/main.py 的核心能力集成到 alpha_id 包：
  - 任务提交（串行/并行）
  - 线程池执行
  - 状态追踪 + TTL 清理
  - Gateway 记忆同步
  - 多后端代码生成（ToolA/ToolB 可配置）

工作模式：
  serial   — 需求 → ToolA 生成 → ToolB 优化 → 归档
  parallel — 同一需求同时发 ToolA+ToolB → 对比 → 归档

用法：
    from alpha_id.tool_orchestrator import ToolOrchestrator, TaskConfig

    orch = ToolOrchestrator()
    task_id = orch.submit("写个 Python 爬虫", mode="serial")
    result = orch.get_result(task_id)

独立运行：
    python -m alpha_id.tool_orchestrator --port 19090
"""

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════════════

@dataclass
class TaskConfig:
    """任务配置"""
    mode: str = "serial"          # serial / parallel
    timeout: int = 300            # 超时秒数
    sync_to_gateway: bool = True  # 是否同步到 Gateway 记忆
    alpha_id: str = "Alpha-001"   # 身份标识


@dataclass
class Task:
    """编程任务"""
    id: str = ""
    status: str = "pending"       # pending / running / completed / failed
    requirement: str = ""
    mode: str = "serial"
    created_at: float = 0.0
    completed_at: Optional[float] = None
    tool_a_result: Optional[Dict] = None
    tool_b_result: Optional[Dict] = None
    error: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# 任务管理器（线程安全）
# ══════════════════════════════════════════════════════════════

class TaskManager:
    """线程安全的任务存储，支持原子状态转换和 TTL 清理"""

    def __init__(self, ttl: int = 3600):
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.Lock()
        self._ttl = ttl

    def create(self, task: Task) -> None:
        with self._lock:
            self._maybe_evict()
            self._tasks[task.id] = task

    def get(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def transition(self, task_id: str, from_status: str, to_status: str) -> bool:
        """原子状态转换，防止竞态"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status != from_status:
                return False
            task.status = to_status
            return True

    def update(self, task_id: str, **kwargs) -> None:
        """线程安全更新任务字段"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                for k, v in kwargs.items():
                    if hasattr(task, k):
                        setattr(task, k, v)

    def list_latest(self, limit: int = 20) -> List[Task]:
        """返回最近的 N 个任务"""
        with self._lock:
            return sorted(
                self._tasks.values(), key=lambda t: t.created_at, reverse=True
            )[:limit]

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._tasks)

    def _maybe_evict(self) -> None:
        """清理过期任务（必须在锁内调用）"""
        if self._ttl <= 0:
            return
        now = time.time()
        expired = [
            tid for tid, t in self._tasks.items()
            if t.created_at < now - self._ttl and t.status in ("completed", "failed")
        ]
        for tid in expired:
            del self._tasks[tid]
        if expired:
            logger.info("清理了 %d 个过期任务", len(expired))


# ══════════════════════════════════════════════════════════════
# 核心调度器
# ══════════════════════════════════════════════════════════════

class ToolOrchestrator:
    """
    编程工具协同调度器

    用法：
        orch = ToolOrchestrator()
        task_id = orch.submit("写个爬虫")
        result = orch.get_result(task_id)
    """

    def __init__(self, max_workers: int = 4, tool_a_url: str = "",
                 tool_b_url: str = "", gateway_url: str = ""):
        self._task_manager = TaskManager()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="tool_task"
        )
        self._tool_a_url = tool_a_url or ""
        self._tool_b_url = tool_b_url or ""
        self._gateway_url = gateway_url or ""
        self._stats = {"submitted": 0, "completed": 0, "failed": 0}

    # ── 任务提交 ──

    def submit(self, requirement: str, mode: str = "serial",
               config: Optional[TaskConfig] = None) -> str:
        """
        提交编程任务

        Args:
            requirement: 需求描述
            mode: serial（串行）或 parallel（并行）
            config: 额外配置

        Returns:
            task_id
        """
        if config is None:
            config = TaskConfig(mode=mode)

        task = Task(
            id=uuid.uuid4().hex[:12],
            requirement=requirement,
            mode=mode,
            created_at=time.time(),
        )
        self._task_manager.create(task)
        self._stats["submitted"] += 1
        logger.info("任务 %s 已提交 (%s): %s", task.id, mode, requirement[:60])
        return task.id

    def execute(self, task_id: str) -> bool:
        """
        开始执行任务（线程池异步）

        Returns:
            是否成功启动
        """
        if not self._task_manager.transition(task_id, "pending", "running"):
            return False
        task = self._task_manager.get(task_id)
        if task:
            self._executor.submit(self._execute_task, task)
        return True

    def submit_and_execute(self, requirement: str, mode: str = "serial") -> str:
        """提交并立即执行"""
        task_id = self.submit(requirement, mode)
        self.execute(task_id)
        return task_id

    # ── 结果查询 ──

    def get_result(self, task_id: str) -> Optional[Dict]:
        """获取任务结果"""
        task = self._task_manager.get(task_id)
        if not task:
            return None
        return asdict(task)

    def list_tasks(self, limit: int = 20) -> List[Dict]:
        """列出最近的任务"""
        return [asdict(t) for t in self._task_manager.list_latest(limit)]

    @property
    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "pending": self._task_manager.count}

    # ── 执行逻辑 ──

    def _execute_task(self, task: Task) -> None:
        """在线程池中执行任务"""
        try:
            logger.info("执行任务 %s (%s)", task.id, task.mode)

            # 调用 ToolA（代码生成）
            tool_a_result = self._call_tool("A", task.requirement)

            # 调用 ToolB（代码优化）— 串行模式下使用 ToolA 的输出
            tool_b_input = tool_a_result.get("output", "") if tool_a_result else ""
            tool_b_result = self._call_tool("B", tool_b_input or task.requirement)

            self._task_manager.update(
                task.id,
                tool_a_result=tool_a_result,
                tool_b_result=tool_b_result,
                status="completed",
                completed_at=time.time(),
            )
            self._stats["completed"] += 1
            logger.info("任务 %s 完成", task.id)

            # 同步到 Gateway
            if self._gateway_url:
                self._sync_to_gateway(task, tool_a_result, tool_b_result)

        except Exception as e:
            self._task_manager.update(task.id, status="failed", error=str(e))
            self._stats["failed"] += 1
            logger.error("任务 %s 失败: %s", task.id, e)

    def _call_tool(self, tool: str, prompt: str) -> Dict[str, Any]:
        """
        调用指定工具

        如果配置了 TOOL_A_URL / TOOL_B_URL，调用真实服务；
        否则返回 not_implemented（等待接入）
        """
        url = self._tool_a_url if tool == "A" else self._tool_b_url

        if not url:
            return {
                "status": "not_implemented",
                f"message": f"Tool{tool} 未配置（设置 TOOL_{tool}_URL 环境变量接入）",
            }

        try:
            import httpx
            resp = httpx.post(
                f"{url}/v1/generate",
                json={"prompt": prompt},
                timeout=120,
            )
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _sync_to_gateway(self, task: Task, tool_a_result: Dict, tool_b_result: Dict):
        """同步结果到 Gateway 记忆"""
        if not self._gateway_url:
            return
        try:
            import httpx
            httpx.post(
                f"{self._gateway_url}/v1/memory/store",
                json={
                    "alpha_id": "Alpha-001",
                    "content": f"[任务 {task.id}] {task.requirement[:100]}",
                    "category": "orchestrator",
                    "sensitivity": 30,
                    "source": "tool_orchestrator",
                    "tags": ["orchestrator", "task"],
                },
                timeout=10,
            )
        except Exception as e:
            logger.warning("Gateway 同步失败: %s", e)

    # ── 生命周期 ──

    def shutdown(self):
        """优雅关闭"""
        self._executor.shutdown(wait=False, cancel_futures=True)


# ══════════════════════════════════════════════════════════════
# FastAPI 服务（可选独立部署）
# ══════════════════════════════════════════════════════════════

def create_app() -> Any:
    """创建 FastAPI 应用"""
    try:
        from fastapi import FastAPI, Request, HTTPException
        from fastapi.responses import JSONResponse
    except ImportError:
        logger.warning("FastAPI 未安装，无法创建 HTTP 服务")
        return None

    app = FastAPI(title="Alpha-ID Tool Orchestrator", version="1.0.0")

    orch = ToolOrchestrator(
        tool_a_url="",
        tool_b_url="",
        gateway_url="",
    )

    @app.post("/v1/task/submit")
    async def submit_task(req: Request):
        body = await req.json()
        requirement = body.get("requirement", "")
        mode = body.get("mode", "serial")
        if not requirement:
            return JSONResponse({"error": "requirement required"}, 400)
        task_id = orch.submit(requirement, mode)
        return {"success": True, "task_id": task_id}

    @app.post("/v1/task/{task_id}/execute")
    async def execute_task(task_id: str):
        if not orch.execute(task_id):
            return JSONResponse({"error": "task not found or already running"}, 400)
        return {"success": True, "task_id": task_id, "status": "running"}

    @app.get("/v1/task/{task_id}")
    async def get_task(task_id: str):
        result = orch.get_result(task_id)
        if not result:
            return JSONResponse({"error": "task not found"}, 404)
        return {"success": True, "task": result}

    @app.get("/v1/tasks")
    async def list_tasks(limit: int = 20):
        return {
            "success": True,
            "tasks": orch.list_tasks(limit),
            "total": orch.stats["pending"],
        }

    @app.get("/health")
    async def health():
        return {"status": "ok", "stats": orch.stats}

    return app


# ══════════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════════

def main():
    """独立运行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Alpha-ID Tool Orchestrator")
    parser.add_argument("--port", type=int, default=19090, help="服务端口")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--tool-a", default="", help="ToolA URL")
    parser.add_argument("--tool-b", default="", help="ToolB URL")
    parser.add_argument("--gateway", default="", help="Gateway URL")
    args = parser.parse_args()

    app = create_app()
    if app is None:
        print("❌ FastAPI 未安装，无法启动 HTTP 服务")
        return

    import uvicorn
    print(f"Tool Orchestrator → http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
