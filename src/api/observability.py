"""
可观测性 API 路由 — /ready, /metrics

/health 端点保留在 main.py 中（已包含详细依赖检查）。
本路由提供就绪检查和 Prometheus 指标暴露。
"""

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from core.observability import (
    check_readiness,
    get_metrics,
    metrics_content_type,
)

router = APIRouter(tags=["observability"])


@router.get("/ready", summary="就绪检查")
def ready() -> dict:
    """Readiness probe — 依赖是否就绪"""
    return check_readiness()


@router.get("/metrics", summary="Prometheus 指标", response_class=PlainTextResponse)
def metrics() -> Response:
    """Prometheus 抓取端点"""
    return Response(
        content=get_metrics(),
        media_type=metrics_content_type(),
    )
