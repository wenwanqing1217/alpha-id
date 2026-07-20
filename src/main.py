"""Alpha-ID API 服务入口"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

# Ensure this module can be imported either as:
#   - `from main import app`  (src dir on sys.path)
#   - `from src.main import app`  (project root on sys.path, common in tests)
_src_dir = Path(__file__).resolve().parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alpha_id.container import Container
from auth.jwt import validate_master_key

# Support both package-style imports (`src.main`) and direct module imports (`main`).
if __package__:
    from .api.identity import router as identity_router
    from .api.risk import router as risk_router
    from .api.social import router as social_router
    from .api.shortdrama import router as shortdrama_router
else:
    from api.identity import router as identity_router
    from api.risk import router as risk_router
    from api.social import router as social_router
    from api.shortdrama import router as shortdrama_router


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
app.include_router(shortdrama_router)


@app.get("/health")
def health():
    """健康检查"""
    return {"status": "ok", "version": "0.2.0", "service": "alpha-id"}
