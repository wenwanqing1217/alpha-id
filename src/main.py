"""Alpha-ID API 服务入口"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.identity import router as identity_router
from api.social import router as social_router
from api.risk import router as risk_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """服务生命周期管理"""
    # 启动：可在此初始化数据库连接池等
    yield
    # 关闭：可在此清理资源


app = FastAPI(
    title="Alpha-ID API",
    description="数字身份智能管理系统 — API 服务",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
