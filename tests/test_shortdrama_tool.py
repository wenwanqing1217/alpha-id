"""Tests for shortdrama automation tool and API routes."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tools.shortdrama_tool import AIContentScanner, ReviewQueue, ShortDramaTool, ShortDramaBrowserAutomation


# ══════════════════════════════════════════════════════════
# ReviewQueue tests
# ══════════════════════════════════════════════════════════


class TestReviewQueue:
    def test_submit_creates_job(self):
        queue = ReviewQueue()
        job = queue.submit(title="Test", content="content", user_id="u1")
        assert job["job_id"].startswith("sd_")
        assert job["status"] == "pending"
        assert job["user_id"] == "u1"
        assert job["title"] == "Test"

    def test_get_existing_job(self):
        queue = ReviewQueue()
        job = queue.submit(title="Test", content="content")
        fetched = queue.get(job["job_id"])
        assert fetched["job_id"] == job["job_id"]

    def test_get_missing_job_returns_none(self):
        queue = ReviewQueue()
        assert queue.get("nonexistent") is None

    def test_list_jobs_default(self):
        queue = ReviewQueue()
        queue.submit(title="A", content="a", user_id="u1")
        queue.submit(title="B", content="b", user_id="u2")
        jobs = queue.list_jobs()
        assert len(jobs) == 2

    def test_list_jobs_filter_by_user_id(self):
        queue = ReviewQueue()
        queue.submit(title="A", content="a", user_id="u1")
        queue.submit(title="B", content="b", user_id="u2")
        jobs = queue.list_jobs(user_id="u1")
        assert len(jobs) == 1
        assert jobs[0]["user_id"] == "u1"

    def test_list_jobs_filter_by_status(self):
        queue = ReviewQueue()
        j1 = queue.submit(title="A", content="a")
        queue.update_status(j1["job_id"], "approved")
        j2 = queue.submit(title="B", content="b")
        jobs = queue.list_jobs(status="approved")
        assert len(jobs) == 1
        assert jobs[0]["status"] == "approved"

    def test_update_ai_scan(self):
        queue = ReviewQueue()
        job = queue.submit(title="A", content="a")
        updated = queue.update_ai_scan(job["job_id"], {"risk_level": "safe"})
        assert updated["ai_scan_result"]["risk_level"] == "safe"

    def test_update_status(self):
        queue = ReviewQueue()
        job = queue.submit(title="A", content="a")
        updated = queue.update_status(job["job_id"], "reviewing")
        assert updated["status"] == "reviewing"

    def test_add_note(self):
        queue = ReviewQueue()
        job = queue.submit(title="A", content="a")
        updated = queue.add_note(job["job_id"], "需要修改标题")
        assert len(updated["notes"]) == 1
        assert updated["notes"][0]["text"] == "需要修改标题"


# ══════════════════════════════════════════════════════════
# AIContentScanner tests
# ══════════════════════════════════════════════════════════


class TestAIContentScanner:
    def test_scan_no_client_returns_unknown(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        scanner = AIContentScanner()
        result = scanner.scan("T", "C")
        assert result["risk_level"] == "unknown"

    def test_scan_calls_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        scanner = AIContentScanner()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"risk_level": "safe", "violations": [], "suggestions": [], "summary": "ok"}'
        mock_client.chat.completions.create.return_value = mock_response
        scanner._client = mock_client
        result = scanner.scan("T", "C")
        assert result["risk_level"] == "safe"


# ══════════════════════════════════════════════════════════
# ShortDramaTool tests
# ══════════════════════════════════════════════════════════


class TestShortDramaTool:
    def test_scan_and_submit_blocked(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        tool = ShortDramaTool()
        tool.scanner = MagicMock()
        tool.scanner.scan.return_value = {
            "risk_level": "blocked",
            "violations": ["色情低俗"],
            "suggestions": ["请修改"],
            "summary": "违规",
        }
        result = tool.scan_and_submit(title="Bad", content="content")
        assert result["status"] == "rejected"
        assert result["rejected_by"] == "ai_local"
        assert "预检拦截" in result["message"]

    def test_scan_and_submit_safe(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        tool = ShortDramaTool()
        tool.scanner = MagicMock()
        tool.scanner.scan.return_value = {
            "risk_level": "safe",
            "violations": [],
            "suggestions": [],
            "summary": "ok",
        }
        result = tool.scan_and_submit(title="Good", content="content")
        assert result["status"] == "reviewing"
        assert "job_id" in result
        assert result["success"] is True

    def test_query_status_existing(self):
        tool = ShortDramaTool()
        job = tool.scan_and_submit(title="T", content="C")
        result = tool.query_status(job["job_id"])
        assert result["success"] is True
        assert result["job_id"] == job["job_id"]

    def test_query_status_missing(self):
        tool = ShortDramaTool()
        result = tool.query_status("nonexistent")
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_approve_job(self):
        tool = ShortDramaTool()
        job = tool.scan_and_submit(title="T", content="C")
        result = tool.approve_job(job["job_id"])
        assert result["success"] is True
        assert result["status"] == "approved"

    def test_reject_job(self):
        tool = ShortDramaTool()
        job = tool.scan_and_submit(title="T", content="C")
        result = tool.reject_job(job["job_id"], reason="违规")
        assert result["success"] is True
        assert result["status"] == "rejected"
        assert "违规" in result["message"]

    def test_list_jobs(self, monkeypatch):
        from tools import shortdrama_tool
        fresh_queue = ReviewQueue()
        monkeypatch.setattr(shortdrama_tool, "_review_queue", fresh_queue)
        tool = ShortDramaTool()
        tool.scan_and_submit(title="A", content="a")
        tool.scan_and_submit(title="B", content="b")
        result = tool.list_jobs()
        assert result["success"] is True
        assert result["total"] == 2


# ══════════════════════════════════════════════════════════
# ReviewQueue persistence tests
# ══════════════════════════════════════════════════════════


class TestReviewQueuePersistence:
    """ReviewQueue 持久化存储测试"""

    def test_no_storage_backward_compatible(self):
        """不传 storage_backend 时行为不变，不持久化"""
        queue = ReviewQueue()
        job = queue.submit(title="T", content="C")
        assert queue.get(job["job_id"]) is not None

    def test_persist_calls_storage_save(self):
        """每次 mutation 后调用 storage.save"""
        mock_storage = MagicMock()
        queue = ReviewQueue(storage_backend=mock_storage)
        job = queue.submit(title="T", content="C")
        assert mock_storage.save.call_count >= 1
        # submit 时应该调用过 save
        mock_storage.save.assert_called_with("shortdrama_jobs", queue._jobs)

    def test_load_on_init(self):
        """初始化时从 storage.load 加载已有数据"""
        existing = {
            "job-1": {
                "job_id": "job-1",
                "title": "Loaded",
                "status": "pending",
            }
        }
        mock_storage = MagicMock()
        mock_storage.load.return_value = existing
        queue = ReviewQueue(storage_backend=mock_storage)
        assert queue.get("job-1") is not None
        assert queue.get("job-1")["title"] == "Loaded"

    def test_load_handles_bad_data(self):
        """load 返回非 dict 时忽略，不崩溃"""
        mock_storage = MagicMock()
        mock_storage.load.return_value = ["not-a-dict"]
        queue = ReviewQueue(storage_backend=mock_storage)
        job = queue.submit(title="T", content="C")
        assert job["job_id"] is not None

    def test_load_handles_exception(self):
        """storage.load 抛异常时忽略，队列仍可用"""
        mock_storage = MagicMock()
        mock_storage.load.side_effect = RuntimeError("db down")
        queue = ReviewQueue(storage_backend=mock_storage)
        job = queue.submit(title="T", content="C")
        assert job["job_id"] is not None

    def test_persist_handles_save_exception(self):
        """storage.save 抛异常时记录 warning，不崩溃"""
        mock_storage = MagicMock()
        mock_storage.save.side_effect = RuntimeError("disk full")
        queue = ReviewQueue(storage_backend=mock_storage)
        job = queue.submit(title="T", content="C")
        assert queue.get(job["job_id"]) is not None

    def test_full_lifecycle_with_json_storage(self, tmp_path):
        """使用真实 JsonStorage 验证完整生命周期"""
        from core.storage import JsonStorage
        db_file = tmp_path / "test_jobs.json"
        storage = JsonStorage(str(db_file))

        # 第一阶段：创建队列并提交任务
        queue1 = ReviewQueue(storage_backend=storage, storage_key="jobs")
        job = queue1.submit(title="P1", content="c1", user_id="u1")
        queue1.update_status(job["job_id"], "reviewing")
        queue1.update_status(job["job_id"], "approved")
        queue1.add_note(job["job_id"], "good")

        # 第二阶段：新建队列实例，验证数据已恢复
        queue2 = ReviewQueue(storage_backend=storage, storage_key="jobs")
        restored = queue2.get(job["job_id"])
        assert restored is not None
        assert restored["status"] == "approved"
        assert len(restored["notes"]) == 1
        assert restored["notes"][0]["text"] == "good"

    def test_full_lifecycle_with_sqlite_storage(self, tmp_path):
        """使用真实 SqliteStorage 验证完整生命周期"""
        from core.storage_sqlite import SqliteStorage
        db_file = tmp_path / "test_jobs.db"
        storage = SqliteStorage(str(db_file))

        queue1 = ReviewQueue(storage_backend=storage, storage_key="drama_jobs")
        job = queue1.submit(title="S1", content="c2", user_id="u2")
        queue1.update_ai_scan(job["job_id"], {"risk_level": "safe"})
        queue1.update_status(job["job_id"], "rejected", review_result={"by": "ai", "reason": "bad"})

        queue2 = ReviewQueue(storage_backend=storage, storage_key="drama_jobs")
        restored = queue2.get(job["job_id"])
        assert restored is not None
        assert restored["status"] == "rejected"
        assert restored["ai_scan_result"]["risk_level"] == "safe"
        assert restored["review_result"]["reason"] == "bad"


# ══════════════════════════════════════════════════════════
# ShortDramaBrowserAutomation tests
# ══════════════════════════════════════════════════════════


class TestShortDramaBrowserAutomation:
    """浏览器自动化 mock 测试（不依赖真实浏览器）"""

    def test_no_playwright_returns_error(self, monkeypatch):
        """Playwright 未安装时返回错误"""
        monkeypatch.setattr("tools.shortdrama_tool.HAS_PLAYWRIGHT", False)
        automation = ShortDramaBrowserAutomation()
        result = automation.open_platform()
        assert result["success"] is False
        assert "Playwright" in result["error"]

    def test_open_platform_with_mock(self, monkeypatch):
        """使用 mock playwright 测试打开平台"""
        monkeypatch.setattr("tools.shortdrama_tool.HAS_PLAYWRIGHT", True)

        mock_page = MagicMock()
        mock_page.url = "https://www.shortdramas.com"
        mock_page.title.return_value = "ShortDramas"

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        with patch("tools.shortdrama_tool.sync_playwright") as mock_sync:
            mock_sync.return_value.start.return_value = mock_pw
            automation = ShortDramaBrowserAutomation(headless=True)
            result = automation.open_platform("https://www.shortdramas.com")

        assert result["success"] is True
        assert "shortdramas" in result["message"]
        assert result["page_title"] == "ShortDramas"

    def test_upload_content_flow_with_mock(self, monkeypatch):
        """使用 mock playwright 测试上传流程"""
        monkeypatch.setattr("tools.shortdrama_tool.HAS_PLAYWRIGHT", True)

        class MockLocator:
            """模拟 Playwright Locator API（.first 返回自身）"""
            def __init__(self, count=1):
                self._count = count
                self.filled = []
                self.clicked = False

            @property
            def first(self):
                return self

            def count(self):
                return self._count

            def fill(self, text):
                self.filled.append(text)

            def click(self):
                self.clicked = True

            def inner_text(self):
                return "提交成功"

        mock_page = MagicMock()
        mock_page.url = "https://www.shortdramas.com/upload"
        mock_page.title.return_value = "Upload"
        mock_page.screenshot.return_value = None

        # 为不同选择器准备 mock locator
        mock_new_btn = MockLocator(count=1)
        mock_title_input = MockLocator(count=1)
        mock_content_input = MockLocator(count=1)
        mock_submit_btn = MockLocator(count=1)
        mock_success = MockLocator(count=1)

        def locator_side_effect(selector):
            if "新建" in selector or "上传" in selector:
                return mock_new_btn
            elif "标题" in selector:
                return mock_title_input
            elif "内容" in selector:
                return mock_content_input
            elif "提交" in selector or "发布" in selector:
                return mock_submit_btn
            elif "成功" in selector:
                return mock_success
            return MockLocator(count=0)

        mock_page.locator.side_effect = locator_side_effect

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        with patch("tools.shortdrama_tool.sync_playwright") as mock_sync:
            mock_sync.return_value.start.return_value = mock_pw
            automation = ShortDramaBrowserAutomation(headless=True)
            automation._playwright = mock_pw
            automation._browser = mock_browser
            automation._context = mock_context
            automation._page = mock_page

            result = automation.upload_content(
                title="测试短剧",
                content="这是一部测试短剧的内容",
            )

        assert result["success"] is True
        assert "steps" in result or "screenshot" in result or "message" in result
        assert mock_title_input.filled, "标题输入框应被填写"
        assert mock_content_input.filled, "内容输入框应被填写"
        assert mock_submit_btn.clicked, "提交按钮应被点击"

    def test_check_status_with_mock(self, monkeypatch):
        """使用 mock playwright 测试状态检查"""
        monkeypatch.setattr("tools.shortdrama_tool.HAS_PLAYWRIGHT", True)

        mock_page = MagicMock()
        mock_page.url = "https://www.shortdramas.com/dashboard"
        mock_page.title.return_value = "Dashboard"
        mock_page.screenshot.return_value = None

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        with patch("tools.shortdrama_tool.sync_playwright") as mock_sync:
            mock_sync.return_value.start.return_value = mock_pw
            automation = ShortDramaBrowserAutomation(headless=True)
            automation._playwright = mock_pw
            automation._browser = mock_browser
            automation._context = mock_context
            automation._page = mock_page

            result = automation.check_status("job-123")

        assert result["success"] is True
        assert result["job_id"] == "job-123"
        assert "screenshot" in result

    def test_close_idempotent(self):
        """close 在未初始化时不会崩溃"""
        automation = ShortDramaBrowserAutomation()
        automation.close()  # 不应抛异常
        assert automation._page is None
        assert automation._browser is None
        assert automation._playwright is None
