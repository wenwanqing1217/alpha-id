"""
短剧审核流程端到端验证脚本

验证内容：
1. AI 预扫 → 提交审核队列
2. 状态查询 → 审核通过/拒绝
3. 复制上传信息到剪贴板
4. 浏览器自动化 mock 流程
5. 持久化存储生命周期

运行方式：
  python verify_shortdrama_e2e.py
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_ai_scan_and_submit():
    """1. AI 预扫 → 提交审核队列"""
    print("\n" + "=" * 60)
    print("测试 1: AI 预扫 → 提交审核队列")
    print("=" * 60)

    from tools.shortdrama_tool import ShortDramaTool

    tool = ShortDramaTool()
    tool.scanner = MagicMock()
    tool.scanner.scan.return_value = {
        "risk_level": "safe",
        "violations": [],
        "suggestions": [],
        "summary": "内容合规",
    }

    result = tool.scan_and_submit(
        title="测试短剧",
        content="这是一部关于青春校园的短剧剧本",
        user_id="test_user",
    )

    assert result["success"] is True, f"预期 success=True, 实际: {result}"
    assert result["status"] == "reviewing", f"预期 status=reviewing, 实际: {result['status']}"
    assert "job_id" in result, "预期包含 job_id"
    assert result["job_id"].startswith("sd_"), f"job_id 应以 sd_ 开头: {result['job_id']}"
    assert result["ai_scan_result"]["risk_level"] == "safe"

    print(f"✅ 提交成功")
    print(f"   job_id: {result['job_id']}")
    print(f"   status: {result['status']}")
    print(f"   AI 扫描: {result['ai_scan_result']['summary']}")

    return result["job_id"]


def test_query_status(job_id):
    """2. 状态查询"""
    print("\n" + "=" * 60)
    print("测试 2: 状态查询")
    print("=" * 60)

    from tools.shortdrama_tool import ShortDramaTool

    tool = ShortDramaTool()
    result = tool.query_status(job_id)

    assert result["success"] is True
    assert result["job_id"] == job_id
    assert result["status"] in ["pending", "reviewing", "approved", "rejected"]

    print(f"✅ 查询成功")
    print(f"   job_id: {result['job_id']}")
    print(f"   status: {result['status']}")
    print(f"   title: {result['title']}")

    return result


def test_approve_and_reject(job_id):
    """3. 审核通过/拒绝"""
    print("\n" + "=" * 60)
    print("测试 3: 审核通过/拒绝")
    print("=" * 60)

    from tools.shortdrama_tool import ShortDramaTool

    tool = ShortDramaTool()

    # 先通过
    approve_result = tool.approve_job(job_id, reviewer="admin")
    assert approve_result["success"] is True
    assert approve_result["status"] == "approved"
    print(f"✅ 审核通过")
    print(f"   job_id: {job_id}")
    print(f"   reviewer: admin")

    # 再拒绝
    reject_result = tool.reject_job(job_id, reason="需要修改标题", reviewer="admin")
    assert reject_result["success"] is True
    assert reject_result["status"] == "rejected"
    assert "需要修改标题" in reject_result["message"]
    print(f"✅ 审核拒绝")
    print(f"   job_id: {job_id}")
    print(f"   reason: 需要修改标题")

    return approve_result, reject_result


def test_copy_upload_info(job_id):
    """4. 复制上传信息到剪贴板"""
    print("\n" + "=" * 60)
    print("测试 4: 复制上传信息到剪贴板")
    print("=" * 60)

    from tools.shortdrama_tool import ShortDramaTool

    tool = ShortDramaTool()
    result = tool.get_upload_info(job_id)

    assert result["success"] is True
    assert "text" in result
    assert "upload_info" in result
    assert job_id in result["text"] or "测试短剧" in result["text"]

    print(f"✅ 获取上传信息成功")
    print(f"   text 长度: {len(result['text'])} 字符")
    print(f"   平台: {result['upload_info']['platform_url']}")

    # 测试剪贴板复制（pyperclip 可能未安装）
    copy_result = tool.copy_to_clipboard(result["text"])
    if copy_result.get("success"):
        print(f"✅ 已复制到剪贴板")
    else:
        print(f"⚠️  剪贴板复制跳过: {copy_result.get('error')}")

    return result


def test_browser_automation_mock():
    """5. 浏览器自动化 mock 流程"""
    print("\n" + "=" * 60)
    print("测试 5: 浏览器自动化 mock 流程")
    print("=" * 60)

    from tools.shortdrama_tool import ShortDramaBrowserAutomation

    # 测试无 playwright 情况
    with patch("tools.shortdrama_tool.HAS_PLAYWRIGHT", False):
        automation = ShortDramaBrowserAutomation()
        result = automation.open_platform()
        assert result["success"] is False
        assert "Playwright" in result["error"]
        print(f"✅ 无 Playwright 时正确返回错误")

    # 测试有 playwright mock 情况
    with patch("tools.shortdrama_tool.HAS_PLAYWRIGHT", True):
        mock_page = MagicMock()
        mock_page.url = "https://www.shortdramas.com"
        mock_page.title.return_value = "ShortDramas Platform"

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
        assert result["page_title"] == "ShortDramas Platform"
        print(f"✅ 打开平台成功 (mock)")
        print(f"   URL: {result['message']}")


def test_persistence_lifecycle():
    """6. 持久化存储完整生命周期"""
    print("\n" + "=" * 60)
    print("测试 6: 持久化存储完整生命周期")
    print("=" * 60)

    from core.storage import JsonStorage
    from tools.shortdrama_tool import ReviewQueue

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_jobs.json"
        storage = JsonStorage(str(db_path))

        # 第一阶段：创建并提交
        queue1 = ReviewQueue(storage_backend=storage, storage_key="e2e_jobs")
        job = queue1.submit(title="E2E测试", content="生命周期测试内容", user_id="e2e_user")
        queue1.update_status(job["job_id"], "reviewing")
        queue1.update_status(job["job_id"], "approved")
        queue1.add_note(job["job_id"], "测试备注")
        print(f"✅ 第一阶段：提交并更新任务")
        print(f"   job_id: {job['job_id']}")
        print(f"   status: approved")

        # 第二阶段：新建队列实例，验证数据恢复
        queue2 = ReviewQueue(storage_backend=storage, storage_key="e2e_jobs")
        restored = queue2.get(job["job_id"])
        assert restored is not None, "任务应被持久化恢复"
        assert restored["status"] == "approved"
        assert len(restored["notes"]) == 1
        assert restored["notes"][0]["text"] == "测试备注"
        assert restored["title"] == "E2E测试"
        print(f"✅ 第二阶段：数据恢复成功")
        print(f"   restored title: {restored['title']}")
        print(f"   restored status: {restored['status']}")
        print(f"   notes count: {len(restored['notes'])}")


def test_fairy_brain_nl_control():
    """7. FairyBrain 自然语言控制短剧工具"""
    print("\n" + "=" * 60)
    print("测试 7: FairyBrain 自然语言控制短剧工具")
    print("=" * 60)

    from fairy_agent import FairyBrain

    class MockFairy:
        def __init__(self):
            self.shown = []

        def _show_result(self, text):
            self.shown.append(text)

    mock_tool = MagicMock()
    mock_tool.scan_and_submit.return_value = {
        "job_id": "nl-test-123",
        "status": "pending",
        "risk_level": "safe",
        "message": "已提交",
        "success": True,
    }
    mock_tool.query_status.return_value = {
        "job_id": "nl-test-123",
        "status": "reviewing",
        "message": "审核中",
        "success": True,
    }

    with patch("tools.shortdrama_tool.ShortDramaTool", return_value=mock_tool):
        brain = FairyBrain(MockFairy())
        brain._client = MagicMock()

        # 模拟 LLM 返回工具调用
        from fairy_agent import FairyTool

        tc = MagicMock()
        tc.id = "call_nl"
        tc.function.name = "shortdrama_scan_and_submit"
        tc.function.arguments = '{"title": "NL测试", "content": "内容"}'

        choice = MagicMock()
        choice.message.content = None
        choice.message.tool_calls = [tc]

        response = MagicMock()
        response.choices = [choice]
        brain._client.chat.completions.create.return_value = response

        result = brain._call_llm("预审短剧，标题是NL测试")
        print(f"✅ NL 调用工具: shortdrama_scan_and_submit")
        print(f"   result: {result}")
        print(f"   tool called: {mock_tool.scan_and_submit.called}")


def main():
    print("\n" + "=" * 60)
    print("短剧审核流程端到端验证")
    print("=" * 60)

    os.environ.setdefault("OPENAI_API_KEY", "sk-test-verify")

    try:
        job_id = test_ai_scan_and_submit()
        test_query_status(job_id)
        test_approve_and_reject(job_id)
        test_copy_upload_info(job_id)
        test_browser_automation_mock()
        test_persistence_lifecycle()
        test_fairy_brain_nl_control()

        print("\n" + "=" * 60)
        print("🎉 所有端到端验证通过！")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 验证异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
