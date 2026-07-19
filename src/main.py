"""Alpha-ID API 服务入口"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alpha_id.container import Container
from auth.jwt import validate_master_key
from .api.identity import router as identity_router
from .api.risk import router as risk_router
from .api.social import router as social_router


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


@app.get("/health")
def health():
    """健康检查"""
    return {"status": "ok", "version": "0.2.0", "service": "alpha-id"}
