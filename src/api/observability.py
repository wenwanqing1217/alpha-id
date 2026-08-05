"""
可观测性 API 路由 — /metrics

/health 与 /ready 端点保留在 main.py 中（基于容器依赖的真实检查）。
本路由提供 Prometheus 指标暴露。
"""

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from core.observability import (
    get_metrics,
    metrics_content_type,
)

router = APIRouter(tags=["observability"])


@router.get("/metrics", summary="Prometheus 指标", response_class=PlainTextResponse)
def metrics() -> Response:
    """Prometheus 抓取端点"""
    return Response(
        content=get_metrics(),
        media_type=metrics_content_type(),
    )
