"""短剧自动化 API 路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.shortdrama_tool import ShortDramaTool
from .models import ShortDramaJobResponse, ShortDramaListResponse, ShortDramaQueryRequest, ShortDramaSubmitRequest

router = APIRouter(prefix="/api/v1/shortdrama", tags=["短剧自动化"])

# 全局短剧工具实例
_shortdrama_tool = ShortDramaTool()


class _ApproveRequest(BaseModel):
    job_id: str
    reviewer: str = "admin"


class _RejectRequest(BaseModel):
    job_id: str
    reason: str
    reviewer: str = "admin"


@router.post("/scan-and-submit", response_model=dict)
async def scan_and_submit(body: ShortDramaSubmitRequest):
    """AI 预扫 + 提交审核队列"""
    try:
        result = _shortdrama_tool.scan_and_submit(
            title=body.title,
            content=body.content,
            content_type=body.content_type,
            user_id=body.user_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query", response_model=dict)
async def query_status(body: ShortDramaQueryRequest):
    """查询审核任务状态"""
    result = _shortdrama_tool.query_status(body.job_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "任务不存在"))
    return result


@router.get("/jobs", response_model=ShortDramaListResponse)
async def list_jobs(user_id: str = "default", status: str = ""):
    """列出审核任务"""
    result = _shortdrama_tool.list_jobs(user_id=user_id, status=status or None)
    return ShortDramaListResponse(**result)


@router.post("/approve", response_model=dict)
async def approve_job(body: _ApproveRequest):
    """人工审核通过"""
    result = _shortdrama_tool.approve_job(body.job_id, reviewer=body.reviewer)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "任务不存在"))
    return result


@router.post("/reject", response_model=dict)
async def reject_job(body: _RejectRequest):
    """人工审核拒绝"""
    result = _shortdrama_tool.reject_job(body.job_id, reason=body.reason, reviewer=body.reviewer)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "任务不存在"))
    return result


class _CopyUploadInfoRequest(BaseModel):
    job_id: str


@router.post("/copy-upload-info", response_model=dict)
async def copy_upload_info(body: _CopyUploadInfoRequest):
    """复制任务的上传信息到剪贴板"""
    job = _shortdrama_tool.queue.get(body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    text = "\n".join([
        job.get("title", ""),
        job.get("content", ""),
    ])
    result = _shortdrama_tool.copy_to_clipboard(text)
    if result.get("success"):
        return result
    return result
