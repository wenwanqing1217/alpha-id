"""Alpha-ID API 服务入口

运行方式：
    python -m src.main
    或安装后：aid-api
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv

# 加载 .env 文件（必须在读取环境变量之前）
load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from alpha_id.container import Container  # noqa: E402
from auth.jwt import validate_master_key  # noqa: E402
from core.middleware import CorrelationIDMiddleware  # noqa: E402
from core.rate_limit import RateLimitMiddleware  # noqa: E402
from core.settings import settings  # noqa: E402

# Support both package-style imports (`src.main`) and direct module imports (`main`).
if __package__:
    from .api.identity import router as identity_router
    from .api.risk import router as risk_router
    from .api.social import router as social_router
    from .api.dual_chain import router as dual_chain_router
    from .api.registration import router as registration_router
    from .api.observability import router as observability_router
else:
    from api.identity import router as identity_router
    from api.risk import router as risk_router
    from api.social import router as social_router
    from api.dual_chain import router as dual_chain_router
    from api.registration import router as registration_router
    from api.observability import router as observability_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """服务生命周期管理"""
    # 启动：校验 JWT 主密钥
    validate_master_key()
    # 启动：容器自动 lazy init
    container = Container.instance()
    yield
    # 关闭：释放资源（HTTP 客户端、LLM 客户端、容器）
    from core.http_client import close_clients
    from core.llm_async import close_llm_client
    await close_llm_client()
    close_clients()
    container.close()


app = FastAPI(
    title="Alpha-ID API",
    description="数字身份智能管理系统 — API 服务",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS - 从统一配置读取
origins = settings.cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流（CORS 内层，CorrelationID 外层）
# 执行顺序：CorrelationId → RateLimit → CORS → Route
app.add_middleware(RateLimitMiddleware)

app.add_middleware(CorrelationIDMiddleware)

app.include_router(identity_router)
app.include_router(social_router)
app.include_router(risk_router)
app.include_router(dual_chain_router)
app.include_router(registration_router)
app.include_router(observability_router)

# ── 前端页面 ──
_templates_dir = Path(__file__).parent / "alpha_id" / "templates"
_static_dir = _templates_dir
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    """Ghost.html 官网首页"""
    html_path = _templates_dir / "ghost.html"
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/health")
def health():
    """真实健康检查：验证关键组件可达性（通过 Container 获取存储后端）"""
    from alpha_id.container import Container

    checks = {"status": "ok", "version": settings.app_version, "service": "alpha-id"}
    container = Container.instance()

    # 1. 存储后端连通性
    try:
        store = container.storage
        # 简单读写验证
        test_key = "__healthcheck__"
        store.save(test_key, {"ts": __import__("datetime").datetime.now().isoformat()})
        store.load(test_key)
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        checks["status"] = "degraded"

    # 2. 用户身份 API 路由
    try:
        stats = container.identity.get_statistics()
        checks["identity"] = f"ok ({stats.total_users} users)"
    except Exception as e:
        checks["identity"] = f"error: {e}"
        checks["status"] = "degraded"

    # 3. 双链记忆存储
    try:
        from core.dual_chain import DualChainManager
        mgr = DualChainManager("did:aid:healthcheck", storage=container.storage)
        stats = mgr.stats()
        checks["memory"] = f"ok (private={stats.private_count}, knowledge={stats.knowledge_count})"
    except Exception as e:
        checks["memory"] = f"error: {e}"
        checks["status"] = "degraded"

    return checks
