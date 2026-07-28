"""
通用工具 — 日历、搜索等基础功能
"""

import logging
from datetime import date

logger = logging.getLogger("mindflow.agents.tools")


def calendar_query(params: dict) -> dict:
    """
    日历查询（读取飞书日历）
    当前为模拟数据，后续对接飞书日历 API
    """
    # 模拟返回今天的日程
    today = date.today()
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]

    return {
        "summary": f"{today} {weekday}",
        "events": [
            {"time": "09:00", "title": "晨会", "location": "线上"},
            {"time": "14:00", "title": "项目评审", "location": "3楼会议室"},
        ],
        "date": today.isoformat(),
        "_note": "模拟数据，后续对接飞书日历API",
    }


def web_search(params: dict) -> dict:
    """
    网页搜索（模拟数据）
    后续可对接搜索引擎 API
    """
    query = params.get("query") or params.get("params", {}).get("query", "")
    original = params.get("params", {}).get("original_text", "")
    text = query or original or ""

    # 如果包含公司名，走公司查询
    if "公司" in text or "企业" in text or "背调" in text:
        from mindflow.agents.interview import company_research
        return company_research({"company": text.replace("公司背景", "").replace("背调", "").replace("查一下", "").replace("帮我", "").strip()})

    return {
        "query": text,
        "results": [],
        "summary": f"搜索: {text[:30]}...",
        "_note": "搜索功能待对接",
    }


import subprocess
import os


def code_runner(params: dict) -> dict:
    """
    编程技能：用本地 AI 引擎执行编程任务
    接收参数: {"prompt": "用户的需求描述"}
    返回: {"content": "生成的代码/解答"}
    """
    prompt = params.get("prompt") or params.get("params", {}).get("prompt", "")
    original = params.get("params", {}).get("original_text", "")
    text = prompt or original or ""

    runner_script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "..", "ghost-main", "feishu-bot", "code_runner.py"
    )
    runner_script = os.path.abspath(runner_script)

    if not os.path.exists(runner_script):
        return {"content": f"编程模块未找到: {runner_script}", "status": "error"}

    try:
        result = subprocess.run(
            ["python", runner_script, text],
            capture_output=True, text=True, timeout=180,
            cwd=os.environ.get("CODE_RUNNER_DIR", os.getcwd()),
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            error = result.stderr.strip()[:300]
            return {"content": f"执行出错: {error}", "status": "error"}
        return {"content": output, "status": "success"}
    except subprocess.TimeoutExpired:
        return {"content": "编程任务超时（180秒）", "status": "timeout"}
    except Exception as e:
        return {"content": f"调用失败: {str(e)}", "status": "error"}


def register_tools(engine):
    """注册通用工具到 Mindflow 引擎"""
    engine.register_tool("calendar", calendar_query)
    engine.register_tool("web_search", web_search)
    engine.register_tool("search", web_search)
    engine.register_tool("code_runner", code_runner)
    engine.register_tool("codex_agent", codex_agent)
    engine.register_tool("chat", llm_chat)
    logger.info("  📋 通用工具已注册")
    return engine
