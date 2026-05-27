from langchain.tools import tool
from langchain.tools import ToolRuntime
from coze_coding_dev_sdk import LLMClient, DocumentGenerationClient
from coze_coding_utils.runtime_ctx.context import new_context
from langchain_core.messages import HumanMessage, SystemMessage
from typing import Any, Dict, List
from datetime import datetime


def _safe_str(value: Any) -> str:
    """安全转换为str"""
    if value is None:
        return ""
    return str(value)


@tool
def optimize_text(
    text: str,
    task: str = "优化",
    runtime: ToolRuntime = None
) -> str:
    """
    优化、改写、润色、翻译文本。

    参数:
        text: 原始文本
        task: 任务类型（优化/改写/润色/翻译/简化/正式化/口语化）

    返回:
        处理后的文本
    """
    try:
        client = LLMClient(ctx=runtime.context if runtime else new_context(method="optimize_text"))

        task_prompts = {
            "优化": "优化这段文本，使其更加流畅、准确、专业。",
            "改写": "改写这段文本，保持原意但改变表达方式。",
            "润色": "润色这段文本，提升文笔和表达效果。",
            "翻译": "将这段文本翻译成英文（如果是英文则翻译成中文）。",
            "简化": "简化这段文本，用更简单易懂的语言表达。",
            "正式化": "将这段文本改写为正式、专业的风格。",
            "口语化": "将这段文本改写为口语化、轻松的风格。"
        }

        prompt = task_prompts.get(task, task_prompts["优化"])

        messages = [
            SystemMessage(content="你是一个专业的文本处理专家，擅长优化、改写、润色和翻译文本。"),
            HumanMessage(content=f"{prompt}\n\n原文：\n{text}")
        ]

        response = client.invoke(
            messages=messages,
            model="doubao-seed-2-0-pro-260215",
            temperature=0.3
        )

        # 提取文本内容
        content = response.content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = " ".join(text_parts)

        return f"✅ 文本{task}完成\n\n{content}"

    except Exception as e:
        return f"❌ 文本处理失败: {str(e)}"


@tool
def write_code(
    task: str,
    language: str = "python",
    runtime: ToolRuntime = None
) -> str:
    """
    编写代码。

    参数:
        task: 任务描述
        language: 编程语言（python/javascript/java/c++/go等）

    返回:
        代码及其说明
    """
    try:
        client = LLMClient(ctx=runtime.context if runtime else new_context(method="write_code"))

        prompt = f"""请用{language}语言完成以下任务：

{task}

要求：
1. 代码完整可运行
2. 添加必要的注释
3. 提供使用示例
4. 说明代码逻辑和设计思路"""

        messages = [
            SystemMessage(content=f"你是一个资深的{language}开发专家，擅长编写高质量、可维护的代码。"),
            HumanMessage(content=prompt)
        ]

        response = client.invoke(
            messages=messages,
            model="doubao-seed-2-0-pro-260215",
            temperature=0.2
        )

        # 提取文本内容
        content = response.content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = " ".join(text_parts)

        return f"✅ 代码生成完成\n\n{content}"

    except Exception as e:
        return f"❌ 代码生成失败: {str(e)}"


@tool
def plan_task(
    goal: str,
    timeframe: str = "week",
    runtime: ToolRuntime = None
) -> str:
    """
    制定任务计划。

    参数:
        goal: 目标描述
        timeframe: 时间范围（day/week/month/year）

    返回:
        任务计划
    """
    try:
        client = LLMClient(ctx=runtime.context if runtime else new_context(method="plan_task"))

        timeframes = {
            "day": "今天",
            "week": "本周",
            "month": "本月",
            "year": "今年"
        }

        time_text = timeframes.get(timeframe, timeframe)

        prompt = f"""请为以下目标制定{time_text}的详细执行计划：

目标: {goal}

要求：
1. 将目标拆解为可执行的小任务
2. 为每个任务设定优先级和预计时间
3. 识别潜在风险和应对措施
4. 提供进度检查点
5. 确保计划切实可行"""

        messages = [
            SystemMessage(content="你是一个专业的项目规划专家，擅长制定详细、可执行的任务计划。"),
            HumanMessage(content=prompt)
        ]

        response = client.invoke(
            messages=messages,
            model="doubao-seed-2-0-pro-260215",
            temperature=0.3
        )

        # 提取文本内容
        content = response.content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = " ".join(text_parts)

        return f"✅ 计划制定完成\n\n{content}"

    except Exception as e:
        return f"❌ 计划制定失败: {str(e)}"


@tool
def analyze_data(
    data: str,
    question: str = "请分析这组数据",
    runtime: ToolRuntime = None
) -> str:
    """
    分析数据。

    参数:
        data: 数据（文本格式，可以是CSV、JSON等）
        question: 分析问题

    返回:
        数据分析结果
    """
    try:
        client = LLMClient(ctx=runtime.context if runtime else new_context(method="analyze_data"))

        prompt = f"""请分析以下数据：

{data}

{question}

要求：
1. 提取关键信息
2. 识别趋势和模式
3. 给出可操作的建议
4. 用图表或表格展示关键数据（如果适用）"""

        messages = [
            SystemMessage(content="你是一个数据分析专家，擅长从数据中发现洞察和机会。"),
            HumanMessage(content=prompt)
        ]

        response = client.invoke(
            messages=messages,
            model="doubao-seed-2-0-pro-260215",
            temperature=0.3
        )

        # 提取文本内容
        content = response.content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = " ".join(text_parts)

        return f"✅ 数据分析完成\n\n{content}"

    except Exception as e:
        return f"❌ 数据分析失败: {str(e)}"


@tool
def provide_emotional_support(
    situation: str,
    feeling: str = None,
    runtime: ToolRuntime = None
) -> str:
    """
    提供情感支持。

    参数:
        situation: 情况描述
        feeling: 情绪描述（可选）

    返回:
        情感支持和建议
    """
    try:
        client = LLMClient(ctx=runtime.context if runtime else new_context(method="provide_emotional_support"))

        feeling_text = f"情绪状态：{feeling}\n" if feeling else ""

        prompt = f"""请为以下情况提供情感支持：

{feeling_text}情况描述：
{situation}

要求：
1. 共情和理解用户的感受
2. 确认情绪的合理性
3. 提供具体的缓解建议
4. 给予积极的鼓励
5. 如果需要，建议寻求专业帮助"""

        messages = [
            SystemMessage(content="你是一个温暖、理解、支持性的心理助手，擅长提供情感支持和压力缓解建议。"),
            HumanMessage(content=prompt)
        ]

        response = client.invoke(
            messages=messages,
            model="doubao-seed-2-0-pro-260215",
            temperature=0.5
        )

        # 提取文本内容
        content = response.content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = " ".join(text_parts)

        return f"💭 情感支持\n\n{content}"

    except Exception as e:
        return f"❌ 情感支持失败: {str(e)}"
