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

# Support both package-style imports (`src.main`) and direct module imports (`main`).
if __package__:
    from .api.identity import router as identity_router
    from .api.risk import router as risk_router
    from .api.social import router as social_router
    from .api.dual_chain import router as dual_chain_router
else:
    from api.identity import router as identity_router
    from api.risk import router as risk_router
    from api.social import router as social_router
    from api.dual_chain import router as dual_chain_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """服务生命周期管理"""
    # 启动：校验 JWT 主密钥
    validate_master_key()
    # 启动：容器自动 lazy init
    container = Container.instance()
    yield
    # 关闭：释放资源
    container.close()


app = FastAPI(
    title="Alpha-ID API",
    description="数字身份智能管理系统 — API 服务",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS - 生产环境必须配置具体域名
allowed_origins = os.environ.get("AID_ALLOWED_ORIGINS", "").strip()
if allowed_origins:
    origins = [o.strip() for o in allowed_origins.split(",") if o.strip()]
else:
    origins = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(identity_router)
app.include_router(social_router)
app.include_router(risk_router)
app.include_router(dual_chain_router)

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
    """健康检查"""
    return {"status": "ok", "version": "0.2.0", "service": "alpha-id"}
